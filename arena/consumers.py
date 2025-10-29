import asyncio
import secrets
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Room, Turn

# ===== ゲーム定数 =====
TURN_SECONDS = 30       # 1ターン制限
DMG_ATTACK = 6          # 通常攻撃
DMG_CHARGED = 15        # チャージ攻撃


class BattleConsumer(AsyncJsonWebsocketConsumer):
    """ターン制リアルタイム・バトル"""

    async def connect(self):
        # 部屋コード
        self.room_code = self.scope["url_route"]["kwargs"]["room_code"]

        # セッションが無くても匿名IDで続行できるようにする
        session = self.scope.get("session", None)
        if session is not None:
            pid = session.get("pid")
            if not pid:
                pid = secrets.token_hex(16)
                session["pid"] = pid
                await database_sync_to_async(session.save)()
            self.player_id = pid
        else:
            # セッションミドルウェア不在時のフォールバック
            self.player_id = secrets.token_hex(16)

        # ルームごとのWSグループ
        self.room_group_name = f"arena_{self.room_code}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # 参加処理 & 現在ターンの存在を保証
        await self.join_room()
        await self.send_state("joined")

        # 監視タスク（締切 or 両者入力で解決）
        asyncio.create_task(self.turn_watcher())

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # ===== DBヘルパ =====
    @database_sync_to_async
    def _get_room(self):
        try:
            return Room.objects.get(code=self.room_code)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def _save_room(self, room: Room):
        room.save()

    @database_sync_to_async
    def _get_or_create_turn(self, room: Room):
        # 現在ターンを常に用意
        turn, _ = Turn.objects.get_or_create(
            room=room,
            number=room.turn,
            defaults={"deadline": room.deadline or timezone.now() + timedelta(seconds=TURN_SECONDS)},
        )
        # 期限が過去なら延長
        if turn.deadline < timezone.now():
            turn.deadline = timezone.now() + timedelta(seconds=TURN_SECONDS)
            turn.save()
        return turn

    # 注意: 次ターン作成は _resolve() の中から**同期関数**で直接呼ぶため
    # デコレータを付けない（そこでDB操作をまとめて行う）
    def _create_next_turn_sync(self, room: Room):
        room.turn += 1
        room.deadline = timezone.now() + timedelta(seconds=TURN_SECONDS)
        room.save()
        Turn.objects.create(room=room, number=room.turn, deadline=room.deadline)

    @database_sync_to_async
    def _join_room(self, room: Room, pid: str):
        changed = False
        if not room.p1_id:
            room.p1_id = pid; changed = True
        elif room.p1_id != pid and not room.p2_id:
            room.p2_id = pid; changed = True
        if changed:
            room.save()
        return (room.p1_id == pid and 1) or (room.p2_id == pid and 2) or 0

    async def join_room(self):
        room = await self._get_room()
        if not room:
            room = Room(code=self.room_code)
            room.deadline = timezone.now() + timedelta(seconds=TURN_SECONDS)
            await self._save_room(room)
            # 最初のターン
            await database_sync_to_async(Turn.objects.create)(
                room=room, number=1, deadline=room.deadline
            )

        seat = await self._join_room(room, self.player_id)
        # 現在ターンの存在を担保
        await self._get_or_create_turn(room)

        if seat == 0:
            await self.send_json({"type": "log", "text": "満室のため観戦モード（未対応）"})
        else:
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "log_msg", "text": f"Player{seat} joined."},
            )

    # ===== クライアントから受信 =====
    async def receive_json(self, content, **kwargs):
        if content.get("type") == "action":
            await self.handle_action(content.get("action", "none"))

    @database_sync_to_async
    def _set_action(self, pid: str, action: str):
        room = Room.objects.get(code=self.room_code)
        turn, _ = Turn.objects.get_or_create(
            room=room,
            number=room.turn,
            defaults={"deadline": room.deadline or timezone.now() + timedelta(seconds=TURN_SECONDS)},
        )

        # チャージ攻撃の使用可否
        if action == "charged_attack":
            if pid == room.p1_id and room.p1_tokens <= 0:
                action = "none"
            if pid == room.p2_id and room.p2_tokens <= 0:
                action = "none"

        # セット
        if pid == room.p1_id:
            turn.p1_action = action
        elif pid == room.p2_id:
            turn.p2_action = action
        turn.save()
        return room, turn

    async def handle_action(self, action: str):
        room, turn = await self._set_action(self.player_id, action)
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "log_msg", "text": "Action received."}
        )
        # 両者入力済みなら即解決
        if turn.p1_action != "none" and turn.p2_action != "none":
            await self.resolve_if_due(force=True)
        else:
            await self.send_state("picked")

    # ===== ターン監視 =====
    async def turn_watcher(self):
        while True:
            await asyncio.sleep(1)
            await self.resolve_if_due()

    @database_sync_to_async
    def _resolve(self, force=False):
        """
        ターン解決ロジック。
        - 両者入力済み or 締切到達で解決
        - ガードは「自分が受ける」ダメージを0にする
        - 次ターンを**同期的に**必ず作る
        """
        now = timezone.now()
        room = Room.objects.get(code=self.room_code)
        turn, _ = Turn.objects.get_or_create(
            room=room,
            number=room.turn,
            defaults={"deadline": room.deadline or now + timedelta(seconds=TURN_SECONDS)},
        )

        if turn.resolved:
            return room, turn, False

        both_input = (turn.p1_action != "none" and turn.p2_action != "none")
        if not force and now < turn.deadline and not both_input:
            # まだ締切前で両者未入力
            return room, turn, False

        # === 同時ダメージ計算 ===
        a1, a2 = turn.p1_action, turn.p2_action

        def dmg(action: str) -> int:
            if action == "attack":
                return DMG_ATTACK
            if action == "charged_attack":
                return DMG_CHARGED
            return 0

        def guarded(action: str) -> bool:
            return action == "guard"

        # 相手から受けるダメージ
        dmg_to_p1 = dmg(a2)
        dmg_to_p2 = dmg(a1)

        # ★ ガードの向き修正：自分がガードしたら自分が受けるダメージ0
        if guarded(a1):
            dmg_to_p1 = 0
        if guarded(a2):
            dmg_to_p2 = 0

        # HP反映
        room.p1_hp = max(0, room.p1_hp - dmg_to_p1)
        room.p2_hp = max(0, room.p2_hp - dmg_to_p2)

        # チャージトークン
        if a1 == "charge":
            room.p1_tokens += 1
        if a2 == "charge":
            room.p2_tokens += 1
        if a1 == "charged_attack" and room.p1_tokens > 0:
            room.p1_tokens -= 1
        if a2 == "charged_attack" and room.p2_tokens > 0:
            room.p2_tokens -= 1

        # 勝敗
        winner = None
        if room.p1_hp <= 0 and room.p2_hp <= 0:
            winner = None
            room.finished = True
        elif room.p1_hp <= 0:
            winner = 2
            room.finished = True
        elif room.p2_hp <= 0:
            winner = 1
            room.finished = True

        turn.resolved = True
        room.winner = winner
        room.save()
        turn.save()

        # 継続時は次ターンを**ここで確実に作る**
        if not room.finished:
            self._create_next_turn_sync(room)

        return room, turn, True

    async def resolve_if_due(self, force: bool = False):
        room, turn, did = await self._resolve(force=force)
        if did:
            msg = f"Turn {turn.number} resolved: P1={turn.p1_action} / P2={turn.p2_action}"
            await self.channel_layer.group_send(
                self.room_group_name, {"type": "log_msg", "text": msg}
            )
        await self.send_state("update")

    # ===== クライアント送信 =====
    async def log_msg(self, event):
        await self.send_json({"type": "log", "text": event["text"]})

    @database_sync_to_async
    def _compose_state(self, pid: str):
        room = Room.objects.get(code=self.room_code)
        turn, _ = Turn.objects.get_or_create(
            room=room,
            number=room.turn,
            defaults={"deadline": room.deadline or timezone.now() + timedelta(seconds=TURN_SECONDS)},
        )

        you_idx = 1 if pid == room.p1_id else 2 if pid == room.p2_id else 0
        you_hp = room.p1_hp if you_idx == 1 else room.p2_hp if you_idx == 2 else 0
        op_hp  = room.p2_hp if you_idx == 1 else room.p1_hp if you_idx == 2 else 0
        you_tk = room.p1_tokens if you_idx == 1 else room.p2_tokens if you_idx == 2 else 0
        op_tk  = room.p2_tokens if you_idx == 1 else room.p1_tokens if you_idx == 2 else 0

        return {
            "turn": room.turn,
            "deadline": (room.deadline or turn.deadline).isoformat(),
            "finished": room.finished,
            "winner": room.winner,
            "you": {"index": you_idx, "hp": you_hp, "tokens": you_tk},
            "op":  {"hp": op_hp,  "tokens": op_tk},
        }

    async def send_state(self, reason: str):
        state = await self._compose_state(self.player_id)
        await self.send_json({"type": "state", **state})


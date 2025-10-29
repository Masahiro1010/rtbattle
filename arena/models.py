# arena/models.py
from django.db import models
from django.utils import timezone

ACTIONS = (
    ("attack", "Attack"),
    ("guard", "Guard"),
    ("charge", "Charge"),
    ("charged_attack", "Charged Attack"),
    ("none", "None"),
)

class Room(models.Model):
    code = models.CharField(max_length=6, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # 参加者（簡易識別）
    p1_id = models.CharField(max_length=64, blank=True, null=True)
    p2_id = models.CharField(max_length=64, blank=True, null=True)

    # ステータス
    p1_hp = models.IntegerField(default=40)
    p2_hp = models.IntegerField(default=40)
    p1_tokens = models.IntegerField(default=0)  # チャージトークン
    p2_tokens = models.IntegerField(default=0)

    # 進行
    turn = models.IntegerField(default=1)
    deadline = models.DateTimeField(default=timezone.now)

    # 決着
    finished = models.BooleanField(default=False)
    winner = models.IntegerField(blank=True, null=True)  # 1 or 2

    def __str__(self):
        return f"Room {self.code}"

class Turn(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="turns")
    number = models.IntegerField()
    deadline = models.DateTimeField()
    resolved = models.BooleanField(default=False)

    p1_action = models.CharField(max_length=16, choices=ACTIONS, default="none")
    p2_action = models.CharField(max_length=16, choices=ACTIONS, default="none")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("room", "number")
        ordering = ["number"]

    def __str__(self):
        return f"Turn {self.number} in {self.room.code}"

# Create your models here.

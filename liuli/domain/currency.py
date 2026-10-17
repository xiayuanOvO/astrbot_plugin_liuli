from dataclasses import dataclass


WEEKDAY_KEYS = (
    "signin_reward_monday",
    "signin_reward_tuesday",
    "signin_reward_wednesday",
    "signin_reward_thursday",
    "signin_reward_friday",
    "signin_reward_saturday",
    "signin_reward_sunday",
)

DEFAULT_WEEKLY_REWARDS = (10, 12, 14, 16, 18, 20, 30)


@dataclass(frozen=True)
class CurrencySettings:
    name: str = "银币"
    weekly_rewards: tuple[int, int, int, int, int, int, int] = DEFAULT_WEEKLY_REWARDS

    def reward_for_weekday(self, weekday: int) -> int:
        if weekday < 0 or weekday > 6:
            raise ValueError("weekday 必须介于 0 和 6 之间")
        return self.weekly_rewards[weekday]


def parse_positive_amount(value: str | int) -> int | None:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, str) and str(amount) != value.strip():
        return None
    return amount if amount > 0 else None

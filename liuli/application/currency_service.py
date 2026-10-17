from datetime import date

from ..domain.currency import CurrencySettings, parse_positive_amount
from .ports.currency_repository import CurrencyRepository


class CurrencyService:
    def __init__(self, repository: CurrencyRepository, settings: CurrencySettings):
        self.repository = repository
        self.settings = settings

    async def balance(self, platform_id: str, player_id: str) -> str:
        amount = await self.repository.get_balance(platform_id, player_id)
        return f"当前余额：{amount} {self.settings.name}"

    async def sign_in(self, platform_id: str, player_id: str, today: date) -> str:
        reward = self.settings.reward_for_weekday(today.weekday())
        claimed, balance = await self.repository.claim_daily_reward(
            platform_id, player_id, today.isoformat(), reward
        )
        if not claimed:
            return f"今天已经签到过啦，当前余额：{balance} {self.settings.name}。"
        return (
            f"签到成功！获得 {reward} {self.settings.name}。"
            f"\n当前余额：{balance} {self.settings.name}"
        )

    async def spend(self, platform_id: str, player_id: str, amount_text: str | None) -> str:
        if amount_text is None:
            return "用法：/消费 数量"
        amount = parse_positive_amount(amount_text)
        if amount is None:
            return "消费数量必须是正整数。用法：/消费 数量"

        balance = await self.repository.spend(platform_id, player_id, amount, "玩家主动消费")
        if balance is None:
            current_balance = await self.repository.get_balance(platform_id, player_id)
            return (
                f"余额不足，当前有 {current_balance} {self.settings.name}，"
                f"无法消费 {amount} {self.settings.name}。"
            )
        return (
            f"已消费 {amount} {self.settings.name}。"
            f"\n当前余额：{balance} {self.settings.name}"
        )

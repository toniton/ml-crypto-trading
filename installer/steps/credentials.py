"""Exchange and LLM API credentials configuration step."""

from installer.context import InstallProfile, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.prompts import prompt_confirm, prompt_password, prompt_text


class CredentialsStep(BaseStep):
    """Collects and stores API keys for exchanges and LLM providers."""

    @property
    def name(self) -> str:
        return "Exchange & LLM Credentials Configuration"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if not context.interactive:
            return True

        if context.profile == InstallProfile.QUICKSTART:
            skip_keys = prompt_confirm(
                "Use placeholder credentials for Quickstart / Paper Trading simulation?",
                default=True,
            )
            if skip_keys:
                console.info("Using simulation placeholders. You can edit .env later for live trading.")
                return True

        self._configure_exchange_keys(context)
        self._configure_llm_keys(context)
        return True

    def _configure_exchange_keys(self, context: InstallerContext) -> None:
        console.info("Configuring Exchange Credentials:")
        wants_cdc = prompt_confirm("Configure Crypto.com Exchange API keys?", default=False)
        if wants_cdc:
            context.credentials.crypto_dot_com_key = prompt_text("Crypto.com API Key")
            context.credentials.crypto_dot_com_secret = prompt_password("Crypto.com Secret Key")

        wants_binance = prompt_confirm("Configure Binance API keys?", default=False)
        if wants_binance:
            context.credentials.binance_key = prompt_text("Binance API Key")
            context.credentials.binance_secret = prompt_password("Binance Secret Key")

    def _configure_llm_keys(self, context: InstallerContext) -> None:
        console.info("Configuring LLM Providers (for AI trading insights & benchmark testing):")
        wants_llm = prompt_confirm("Configure AI / LLM API keys now?", default=False)
        if not wants_llm:
            return

        context.credentials.deepseek_key = prompt_password("DeepSeek API Key (press Enter to skip)")
        context.credentials.gemini_key = prompt_password("Gemini API Key (press Enter to skip)")
        context.credentials.groq_key = prompt_password("Groq API Key (press Enter to skip)")

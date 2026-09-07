"""Playwright-driven WhatsApp Web client for sending notes to yourself."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from playwright.async_api import BrowserContext, Page, async_playwright

from immepe_bot.config import Settings

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com/"

# WhatsApp Web pins the "Message yourself" chat with the "(You)" suffix.
SELF_CHAT_SELECTOR = 'span[title$="(You)"]'
CHAT_LIST_SELECTOR = 'div[aria-label][role="grid"], #pane-side'
MESSAGE_BOX_SELECTOR = 'div[contenteditable="true"][data-tab="10"]'


@dataclass(slots=True)
class WhatsAppClient:
    """Thin wrapper around a logged-in WhatsApp Web page."""

    page: Page
    settings: Settings

    async def wait_until_ready(self) -> None:
        """Block until the chat list is rendered, i.e. the session is authenticated."""
        logger.info("Waiting for WhatsApp Web session (scan the QR code if prompted)")
        await self.page.wait_for_selector(
            CHAT_LIST_SELECTOR, timeout=self.settings.timeout_ms
        )
        logger.info("WhatsApp Web session is ready")

    async def open_self_chat(self) -> None:
        """Open the 'Message yourself' chat."""
        chat = self.page.locator(SELF_CHAT_SELECTOR).first
        await chat.wait_for(timeout=self.settings.timeout_ms)
        await chat.click()

    async def send(self, message: str) -> None:
        """Send `message` to the currently open chat."""
        if not message.strip():
            raise ValueError("Message must not be empty")

        box = self.page.locator(MESSAGE_BOX_SELECTOR).first
        await box.wait_for(timeout=self.settings.timeout_ms)
        await box.click()
        # WhatsApp sends on Enter, so multi-line text needs Shift+Enter between lines.
        for index, line in enumerate(message.split("\n")):
            if index:
                await self.page.keyboard.press("Shift+Enter")
            await self.page.keyboard.type(line)
        await self.page.keyboard.press("Enter")
        logger.info("Message sent (%d characters)", len(message))


@asynccontextmanager
async def whatsapp_session(settings: Settings) -> AsyncIterator[WhatsAppClient]:
    """Launch a persistent browser context so the login survives restarts."""
    settings.profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context: BrowserContext = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.profile_dir),
            headless=settings.headless,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(WHATSAPP_URL, timeout=settings.timeout_ms)
            client = WhatsAppClient(page=page, settings=settings)
            await client.wait_until_ready()
            yield client
        finally:
            await context.close()

"""Playwright-driven WhatsApp Web client for sending notes to yourself."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from immepe_bot.config import Settings

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com/"

# The "Message yourself" chat carries no stable marker in the sidebar: the "(You)"
# label WhatsApp Web shows lives in the opened conversation's text, never as a chat-
# list `title` attribute, so it cannot be matched there. Instead we match the chat by
# its list label, which is the user's own display name (Settings.self_chat_title) —
# locale-independent, since a name is not translated UI chrome.
CHAT_LIST_SELECTOR = 'div[aria-label][role="grid"], #pane-side'
MESSAGE_BOX_SELECTOR = 'div[contenteditable="true"][data-tab="10"]'
# Submit by clicking the send button rather than pressing Enter, so we do not depend
# on the "Enter is send" WhatsApp setting. Match it by icon, which is not localized.
SEND_BUTTON_SELECTOR = (
    'button:has(span[data-icon="wds-ic-send-filled"]), '
    'button:has(span[data-icon="send"])'
)

# data-id of the last message row in the open chat, or null if there is none. Captured
# before submitting so we can wait for *our* new message rather than a prior one.
_LAST_MESSAGE_ID_JS = """
() => {
  const rows = document.querySelectorAll('#main [data-id]');
  const last = rows[rows.length - 1];
  return last ? last.getAttribute('data-id') : null;
}
"""

# WhatsApp reports delivery status only through an SVG <title> holding a design-system
# icon id ("wds-ic-status-pending" while queued, then a check/read icon once the server
# has the message). The id is not localized, unlike the aria-label. We require a *new*
# last row (data-id != the one seen before submit) so a previously-sent message cannot
# be mistaken for ours, then require it to have left the pending state.
_WAIT_UNTIL_TRANSMITTED_JS = """
(prevId) => {
  const rows = document.querySelectorAll('#main [data-id]');
  const last = rows[rows.length - 1];
  if (!last || last.getAttribute('data-id') === prevId) return false;  // not ours yet
  const titles = Array.from(last.querySelectorAll('svg title'))
    .map(t => (t.textContent || '').trim())
    .filter(v => v.startsWith('wds-ic-'));
  if (!titles.length) return false;                   // status not rendered yet
  return !titles.includes('wds-ic-status-pending');   // left the pending state
}
"""


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
        """Open the 'Message yourself' chat, found by your display name."""
        title = self.settings.self_chat_title
        if not title:
            raise ValueError(
                "self_chat_title is not set. Set IMMEPE_SELF_CHAT_TITLE to your "
                "WhatsApp display name (the label on your 'Message yourself' chat, "
                "shown at the top of your chat list)."
            )
        # get_by_title(exact=True) matches the [title] attribute without hand-building
        # a CSS selector, so names with quotes/spaces are handled safely.
        chat = (
            self.page.locator(CHAT_LIST_SELECTOR).get_by_title(title, exact=True).first
        )
        await chat.wait_for(timeout=self.settings.timeout_ms)
        await chat.click()

    async def send(self, message: str) -> None:
        """Type, submit, and confirm delivery of `message` to the open chat."""
        if not message.strip():
            raise ValueError("Message must not be empty")

        box = self.page.locator(MESSAGE_BOX_SELECTOR).first
        await box.wait_for(timeout=self.settings.timeout_ms)
        await box.click()
        # Type the text using Shift+Enter for newlines so a plain Enter is never
        # needed to insert them; the message is submitted explicitly below.
        for index, line in enumerate(message.split("\n")):
            if index:
                await self.page.keyboard.press("Shift+Enter")
            await self.page.keyboard.type(line)

        # Note the current last message so the delivery wait can tell ours apart.
        previous_last_id = await self.page.evaluate(_LAST_MESSAGE_ID_JS)
        await self._submit()
        await self._wait_until_transmitted(previous_last_id)
        logger.info("Message sent (%d characters)", len(message))

    async def _submit(self) -> None:
        """Click the send button, falling back to Enter on older layouts."""
        button = self.page.locator(SEND_BUTTON_SELECTOR).first
        try:
            await button.wait_for(timeout=self.settings.timeout_ms)
            await button.click()
        except PlaywrightTimeoutError:
            # No send button found: rely on Enter, which sends when the WhatsApp
            # "Enter is send" setting is enabled.
            await self.page.keyboard.press("Enter")

    async def _wait_until_transmitted(self, previous_last_id: str | None) -> None:
        """Block until the newly sent message leaves the pending state.

        `previous_last_id` is the last message's id from before submitting, so a
        message sent earlier is never mistaken for this one. The session's context is
        closed as soon as `send` returns; without this wait the browser can shut down
        before WhatsApp flushes the message to its servers, so it is written into the
        chat locally but never delivered. If the message stays pending (e.g. no
        connectivity) this raises `PlaywrightTimeoutError` rather than silently
        reporting success.
        """
        await self.page.wait_for_function(
            _WAIT_UNTIL_TRANSMITTED_JS,
            arg=previous_last_id,
            timeout=self.settings.timeout_ms,
        )


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

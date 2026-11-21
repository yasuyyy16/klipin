"""INT-02: baca chat replay YouTube (yt-dlp `live_chat`, JSON-lines) → Pesan Chat."""

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# renderer item chat → `chat_messages.kind`; renderer lain (pesan sistem, ticker) diabaikan
_KINDS = {
    "liveChatTextMessageRenderer": "text",
    "liveChatPaidMessageRenderer": "donation",
    "liveChatPaidStickerRenderer": "donation",
    "liveChatMembershipItemRenderer": "membership",
    "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer": "membership",
    "liveChatSponsorshipsGiftRedemptionAnnouncementRenderer": "membership",
}


@dataclass(frozen=True)
class ChatMessage:
    offset_ms: int
    author: str | None
    message: str
    kind: str


def _runs_text(node: dict[str, Any] | None) -> str:
    """Teks dari `{"runs": [...]}` / `{"simpleText": ...}`; emoji standar → karakternya."""
    if not node:
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    parts = []
    for run in node.get("runs", []):
        if "text" in run:
            parts.append(run["text"])
        elif emoji := run.get("emoji"):
            shortcuts = emoji.get("shortcuts") or []
            if emoji.get("isCustomEmoji") and shortcuts:
                parts.append(shortcuts[0])
            else:
                parts.append(emoji.get("emojiId") or (shortcuts[0] if shortcuts else ""))
    return "".join(parts)


def _item_message(renderer: str, item: dict[str, Any]) -> str:
    text = _runs_text(item.get("message"))
    if not text and renderer == "liveChatMembershipItemRenderer":
        text = _runs_text(item.get("headerSubtext")) or _runs_text(item.get("headerPrimaryText"))
    if not text and renderer == "liveChatPaidStickerRenderer":
        text = _runs_text(item.get("purchaseAmountText"))
    if not text and "Sponsorships" in renderer:
        header = item.get("header", {}).get("liveChatSponsorshipsHeaderRenderer", {})
        text = _runs_text(header.get("primaryText")) or _runs_text(item.get("message"))
    return text


def parse_line(line: str) -> list[ChatMessage]:
    """Satu baris JSON `replayChatItemAction` → 0..n Pesan Chat. Baris rusak → []."""
    try:
        data = json.loads(line)
        replay = data["replayChatItemAction"]
        offset_ms = int(replay.get("videoOffsetTimeMsec") or data.get("videoOffsetTimeMsec"))
    except (ValueError, KeyError, TypeError):
        return []
    out = []
    for action in replay.get("actions", []):
        item_wrap = (action.get("addChatItemAction") or {}).get("item") or {}
        for renderer, item in item_wrap.items():
            kind = _KINDS.get(renderer)
            if kind is None:
                continue
            author = _runs_text(item.get("authorName")) or None
            out.append(ChatMessage(offset_ms, author, _item_message(renderer, item), kind))
    return out


def parse_file(path: Path) -> Iterator[ChatMessage]:
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                yield from parse_line(line)


def reaction_matcher(words: Iterable[str]):
    """FR-010: kata reaksi cocok sebagai kata utuh (tanpa beda huruf besar/kecil);
    emoji/simbol cocok sebagai potongan teks di mana saja."""
    alnum = sorted({w.lower() for w in words if w and re.fullmatch(r"\w+", w)})
    symbols = [w for w in words if w and not re.fullmatch(r"\w+", w)]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, alnum)) + r")(?!\w)",
                         re.IGNORECASE) if alnum else None

    def is_reaction(message: str) -> bool:
        return bool(pattern and pattern.search(message)) or any(s in message for s in symbols)

    return is_reaction

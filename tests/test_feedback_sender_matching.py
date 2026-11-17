"""Unit tests for Telegram feedback routing by sender name."""

from __future__ import annotations

import unittest

from digest.config import SenderConfig
from digest.feedback import _sender_feedback


class SenderFeedbackRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.money_stuff = SenderConfig(
            name="Money Stuff by Matt Levine", from_addr="money@example.com"
        )
        self.axios = SenderConfig(name="Axios Atlanta", from_addr="atlanta@axios.com")
        self.senders = [self.money_stuff, self.axios]

    def test_full_sender_name_routes_to_sender(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "for Money Stuff by Matt Levine, keep the financial regulation stories",
            self.senders,
        )

        self.assertIs(sender, self.money_stuff)
        self.assertEqual(feedback, "keep the financial regulation stories")
        self.assertFalse(unknown)

    def test_publication_alias_routes_to_sender(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "Money Stuff: skip crypto stories", self.senders
        )

        self.assertIs(sender, self.money_stuff)
        self.assertEqual(feedback, "skip crypto stories")
        self.assertFalse(unknown)

    def test_author_alias_routes_to_sender(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "for Matt Levine, emphasize interesting legal analysis", self.senders
        )

        self.assertIs(sender, self.money_stuff)
        self.assertEqual(feedback, "emphasize interesting legal analysis")
        self.assertFalse(unknown)

    def test_alias_matching_ignores_case_and_extra_spaces(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "for   mAtT   LeViNe: keep the odd stories", self.senders
        )

        self.assertIs(sender, self.money_stuff)
        self.assertEqual(feedback, "keep the odd stories")
        self.assertFalse(unknown)

    def test_configured_sender_without_by_uses_full_name(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "axios atlanta: only local news", self.senders
        )

        self.assertIs(sender, self.axios)
        self.assertEqual(feedback, "only local news")
        self.assertFalse(unknown)

    def test_unknown_explicit_sender_is_not_routed_globally(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "for Unknown Newsletter, focus on housing", self.senders
        )

        self.assertIsNone(sender)
        self.assertEqual(feedback, "focus on housing")
        self.assertTrue(unknown)

    def test_ambiguous_alias_is_not_routed_to_either_sender(self) -> None:
        another_sender = SenderConfig(
            name="Markets by Matt Levine", from_addr="markets@example.com"
        )

        sender, feedback, unknown = _sender_feedback(
            "for Matt Levine, skip politics", [self.money_stuff, another_sender]
        )

        self.assertIsNone(sender)
        self.assertEqual(feedback, "skip politics")
        self.assertTrue(unknown)

    def test_unprefixed_feedback_targets_global_profile(self) -> None:
        sender, feedback, unknown = _sender_feedback(
            "Avoid sports in every newsletter", self.senders
        )

        self.assertIsNone(sender)
        self.assertEqual(feedback, "Avoid sports in every newsletter")
        self.assertFalse(unknown)


if __name__ == "__main__":
    unittest.main()

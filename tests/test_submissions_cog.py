"""Tests for the submissions cog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


@pytest.mark.asyncio
class TestSubmissionsCog:
    async def test_submission_approve_happy_path(self) -> None:
        from src.cogs.submissions import Submissions

        bot = MagicMock()
        cog = Submissions(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        mock_gs = MagicMock(id=1)

        with (
            patch("src.cogs.submissions.submissions_service") as mock_sub_service,
            patch("src.cogs.submissions.audit_service") as mock_audit,
            patch("src.cogs.submissions.gs_service") as mock_gs_service,
        ):
            mock_gs_service.get_or_create = AsyncMock(return_value=mock_gs)
            mock_sub_service.approve_submission = AsyncMock()
            mock_audit.log_action = AsyncMock()

            await cog.submission_approve.callback(cog, interaction, 1, "note")

            mock_sub_service.approve_submission.assert_called_once_with(1, "222", note="note")
            mock_audit.log_action.assert_called_once_with(
                1,
                "approve_submission",
                "222",
                target_type="submission",
                target_id=1,
            )
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "approved" in args.lower()

    async def test_submission_reject_happy_path(self) -> None:
        from src.cogs.submissions import Submissions

        bot = MagicMock()
        cog = Submissions(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        mock_gs = MagicMock(id=1)

        with (
            patch("src.cogs.submissions.submissions_service") as mock_sub_service,
            patch("src.cogs.submissions.audit_service") as mock_audit,
            patch("src.cogs.submissions.gs_service") as mock_gs_service,
        ):
            mock_gs_service.get_or_create = AsyncMock(return_value=mock_gs)
            mock_sub_service.reject_submission = AsyncMock()
            mock_audit.log_action = AsyncMock()

            await cog.submission_reject.callback(cog, interaction, 1, "Fake evidence")

            mock_sub_service.reject_submission.assert_called_once_with(1, "222", "Fake evidence")
            mock_audit.log_action.assert_called_once_with(
                1,
                "reject_submission",
                "222",
                target_type="submission",
                target_id=1,
            )
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "rejected" in args.lower()

    async def test_submission_list(self) -> None:
        from src.cogs.submissions import Submissions

        bot = MagicMock()
        cog = Submissions(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        mock_sub = MagicMock()
        mock_sub.id = 1
        mock_sub.questions_solved = 5
        mock_sub.verification_status = "pending"
        mock_sub.claimed_rank = 10
        mock_sub.claimed_rating_before = 1500
        mock_sub.claimed_rating_after = 1600
        mock_sub.guild_member.user.discord_user_id = "333"

        with patch("src.cogs.submissions.submissions_service") as mock_sub_service:
            mock_sub_service.list_submissions = AsyncMock(return_value=[mock_sub])

            await cog.submission_list.callback(cog, interaction, 1, "pending")

            mock_sub_service.list_submissions.assert_called_once_with(1, "111", status="pending")
            interaction.followup.send.assert_called_once()
            kwargs = interaction.followup.send.call_args.kwargs
            assert "embed" in kwargs
            assert "Submissions for Event 1" in kwargs["embed"].title
            assert "Submission by <@333>" in kwargs["embed"].fields[0].name

    async def test_modal_invalid_questions_solved(self) -> None:
        from src.cogs.submissions import SubmitResultsModal

        modal = SubmitResultsModal(1)

        # TextInput.value is read-only in discord.py, so replace the field
        modal.questions_solved = MagicMock()
        modal.questions_solved.value = "abc"
        modal.claimed_rank = MagicMock()
        modal.claimed_rank.value = ""
        modal.rating_input = MagicMock()
        modal.rating_input.value = ""
        modal.evidence_url = MagicMock()
        modal.evidence_url.value = ""
        modal.reflection = MagicMock()
        modal.reflection.value = ""

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        await modal.on_submit(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True, thinking=True)
        interaction.followup.send.assert_called_once()
        args = interaction.followup.send.call_args.args[0]
        assert "Invalid input" in args

    async def test_modal_invalid_url(self) -> None:
        from src.cogs.submissions import SubmitResultsModal

        modal = SubmitResultsModal(1)

        modal.questions_solved = MagicMock()
        modal.questions_solved.value = "3"
        modal.claimed_rank = MagicMock()
        modal.claimed_rank.value = ""
        modal.rating_input = MagicMock()
        modal.rating_input.value = ""
        modal.evidence_url = MagicMock()
        modal.evidence_url.value = "invalid_url"
        modal.reflection = MagicMock()
        modal.reflection.value = ""

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        await modal.on_submit(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True, thinking=True)
        interaction.followup.send.assert_called_once()
        args = interaction.followup.send.call_args.args[0]
        assert "Invalid input" in args
        assert "http" in args

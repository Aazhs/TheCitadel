# Server Configuration Guide

This guide covers how server administrators can configure **The Citadel** bot for their Discord server.

---

## 1. Overview

Before **The Citadel** can post welcome messages, announce competitive programming updates, or send contest reminders in your server, it must be configured per-server. Administrators set specific channels for onboarding, announcements, and alerts, as well as a role to ping for upcoming contest notifications.

---

## 2. Setup Commands

All administrative setup is managed through the `/setup` slash command group.

### Configuration Commands Summary:

- **`/setup onboarding-channel #channel`**
  - **Description:** Sets the text channel where welcome messages are posted for new server members.
  - **Behavior:** The bot validates that it has permission to view the channel and post messages in it.

- **`/setup announcement-channel #channel`**
  - **Description:** Sets the channel for general bot announcements and updates.

- **`/setup contest-alert-channel #channel`**
  - **Description:** Sets the channel where contest reminders and upcoming competitive programming alert notifications are posted.

- **`/setup alert-role @role`**
  - **Description:** Sets the role that will be pinged when contest alert notifications are sent.
  - **Behavior:** The bot verifies Discord's role hierarchy to check if the specified role is below the bot's highest role.

- **`/setup view`**
  - **Description:** Displays an embed summarizing the current channel and role configuration settings for the server.

- **`/setup reset`**
  - **Description:** Clears all configured channels and alert role settings for the server.
  - **Behavior:** Displays an interactive confirmation prompt with **Yes** and **Cancel** buttons before clearing configuration.
  - **Note:** Resetting configuration **does NOT** delete member profiles, linked coding handles, or contest event data.

---

## 3. Account Linking & Profiles

Members can link their competitive programming accounts to build a profile within the server.

- **`/link-codeforces <handle>`**: Link a Codeforces account. The bot securely validates the handle through the official API and assigns a "Verified Competitor" role upon success.
- **`/unlink <platform>`**: Unlink a previously connected account. If no active accounts remain, the competitor role is removed.
- **`/my-profile`**: Display your active linked accounts.
- **`/profile <member>`**: View the linked competitive programming profiles of another server member.

---

## 4. Contest Discovery & Reminders

The Citadel automatically syncs upcoming Codeforces contests behind the scenes (every 6 hours) and manages server-wide alert reminders.

### User Commands:
- **`/upcoming`**: Shows the next 5 upcoming Codeforces contests natively in Discord, automatically parsing the division and adapting to each user's local timezone.
- **`/reminders list`**: Displays all upcoming reminders scheduled to be sent to this server's alert channel.

### Admin Commands:
- **`/refresh-codeforces-contests`**: Forces an immediate manual sync of the contest database and reports how many events were updated.
- **`/reminders status`**: Checks if reminders are enabled and verifies the configured channel/role.
- **`/reminders test`**: Generates a test alert embed in the configured alert channel to verify permissions and formatting.
- **`/reminders enable` / `/reminders disable`**: Globally toggles automatic contest reminders for the server.

> **Note on Reminders**: When enabled and configured with `/setup contest-alert-channel`, the bot will automatically send a rich embed alert **24 hours**, **1 hour**, and **10 minutes** before every Codeforces contest begins, pinging the configured `/setup alert-role` if set.

---

## 5. Channel Validation

Whenever an administrator configures a channel using `/setup onboarding-channel`, `/setup announcement-channel`, or `/setup contest-alert-channel`, The Citadel performs automatic permission validation:

1. **Permission Check:** The bot verifies it possesses both **View Channel** and **Send Messages** permissions in the targeted channel.
2. **Validation Feedback:** If any required permissions are missing, the bot returns an immediate error message detailing exactly which permissions must be granted to the bot in that channel's permissions settings.

---

## 6. Role Hierarchy Check

When configuring an alert role with `/setup alert-role @role`, the bot checks Discord's role hierarchy:

- **Hierarchy Verification:** The bot checks whether the selected role is positioned **below** the bot's highest role in the server's role list.
- **Warning State:** If the configured role is above the bot's role, the bot cannot mention that role. The bot will display a warning explaining the role hierarchy issue, but will still save the setting. Administrators can resolve this by moving the bot's role higher in Server Settings > Roles.

---

## 7. Welcome Messages

The Citadel automates member onboarding when configured:

- **Trigger:** When a new member joins the server (`on_member_join`), the bot checks if an onboarding channel has been set via `/setup onboarding-channel`.
- **Behavior:**
  - **Channel Configured:** The bot posts a rich welcome embed tagging the new member and directing them to run the `/start` command.
  - **No Channel Configured:** If no onboarding channel is set, the bot takes no action.

---

## 8. The `/start` Command

The `/start` command is available to all server members (not limited to administrators).

- **Type:** Member onboarding command.
- **Visibility:** Returns an **ephemeral** message (visible only to the user who ran the command).
- **Contents:** Guides new members through essential setup steps:
  1. Linking their competitive programming profiles (e.g., Codeforces, LeetCode).
  2. Opting into contest alerts and notifications.
  3. Checking upcoming competitive programming contests.

---

## 9. Troubleshooting

If you encounter issues while using or configuring The Citadel, check the common resolution steps below:

### 1. Bot doesn't send welcome messages
- **Check Configuration:** Verify that an onboarding channel is configured by running `/setup view`.
- **Check Permissions:** Ensure the bot has **View Channel** and **Send Messages** permissions in the designated onboarding channel.
- **Check Developer Intents:** Ensure the bot host has enabled the **Server Members Intent** in the Discord Developer Portal under the Bot tab.

### 2. Bot can't mention the alert role
- **Check Role Hierarchy:** Ensure the bot's role is positioned **above** the configured alert role in **Server Settings** > **Roles**.
- **Check Permission:** Ensure the bot has the **Mention Everyone** permission enabled on the server or channel level.

### 3. Slash commands not showing up
- **Wait for Sync:** Global slash command updates can take up to an hour to propagate across Discord.
- **Re-invite Bot:** Ensure the bot was invited with the `applications.commands` scope selected. Re-invite the bot using the generated OAuth2 URL if necessary.

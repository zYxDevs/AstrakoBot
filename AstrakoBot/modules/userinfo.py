import html
import re
import os
import requests

from telegram.user import User
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import ChannelParticipantsAdmins
from telethon import events, types

from telegram import MAX_MESSAGE_LENGTH, ParseMode, Update, MessageEntity
from telegram.ext import CallbackContext, CommandHandler, Filters
from telegram.ext.dispatcher import run_async
from telegram.error import BadRequest
from telegram.utils.helpers import escape_markdown, mention_html
from telethon.errors import (
    ChannelInvalidError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    PeerIdInvalidError,
    UserNotParticipantError,
)

from AstrakoBot import (
    DEV_USERS,
    OWNER_ID,
    SUDO_USERS,
    SUPPORT_USERS,
    WHITELIST_USERS,
    INFOPIC,
    dispatcher,
    sw,
)
from AstrakoBot.__main__ import STATS, GDPR, TOKEN, USER_INFO
import AstrakoBot.modules.sql.userinfo_sql as sql
from AstrakoBot.modules.disable import DisableAbleCommandHandler
from AstrakoBot.modules.sql.global_bans_sql import is_user_gbanned
from AstrakoBot.modules.sql.afk_sql import is_afk, check_afk_status
from AstrakoBot.modules.sql.users_sql import get_user_num_chats
from AstrakoBot.modules.sql.clear_cmd_sql import get_clearcmd
from AstrakoBot.modules.helper_funcs.chat_status import sudo_plus
from AstrakoBot.modules.helper_funcs.extraction import extract_user
from AstrakoBot.modules.helper_funcs.misc import delete
from AstrakoBot import telethn as AstrakoBotTelethonClient, SUDO_USERS, SUPPORT_USERS

def get_id(update: Update, context: CallbackContext):
    bot, args = context.bot, context.args
    message = update.effective_message
    chat = update.effective_chat
    msg = update.effective_message
    user_id = extract_user(msg, args)

    if user_id:

        if msg.reply_to_message and msg.reply_to_message.forward_from:

            user1 = message.reply_to_message.from_user
            user2 = message.reply_to_message.forward_from

            msg.reply_text(
                f"<b>Telegram ID</b>\n"
                f"• {html.escape(user2.first_name)}: <code>{user2.id}</code>\n"
                f"• {html.escape(user1.first_name)}: <code>{user1.id}</code>",
                parse_mode=ParseMode.HTML,
            )

        else:
            try:
                user = bot.get_chat(user_id)
                msg.reply_text(
                    f"{html.escape(user.first_name)}'s id is <code>{user.id}</code>.",
                    parse_mode=ParseMode.HTML,
                )
            except:
                msg.reply_text(
                    f"Their id is <code>{user_id}</code>.",
                    parse_mode=ParseMode.HTML,
                )

    else:

        if chat.type == "private":
            msg.reply_text(
                f"Your id is <code>{chat.id}</code>", parse_mode=ParseMode.HTML
            )

        else:
            msg.reply_text(
                f"This group's id is <code>{chat.id}</code>", parse_mode=ParseMode.HTML
            )


@AstrakoBotTelethonClient.on(
    events.NewMessage(pattern="/ginfo ", from_users=(SUDO_USERS or []) + (SUPPORT_USERS or []))
)
async def group_info(event) -> None:
    target_entity = None
    entity_id_str = None

    if event.is_reply:
        replied_msg = await event.get_reply_message()
        if replied_msg and replied_msg.sender_id:
            target_entity = replied_msg.sender_id
            entity_id_str = str(target_entity)
        else:
            await event.reply("Could not identify the user from the replied message.")
            return
    else:
        parts = event.text.split(" ", 1)
        if len(parts) > 1:
            entity_id_str = parts[1].strip()
            if entity_id_str.startswith('@'):
                target_entity = entity_id_str
            else:
                try:
                    target_entity = int(entity_id_str)
                except ValueError:
                    await event.reply("Invalid ID or username format.")
                    return
        else:
            target_entity = event.chat_id
            entity_id_str = str(target_entity)

    if target_entity is None:
        await event.reply("Could not determine the target entity.")
        return

    try:
        entity = await event.client.get_entity(target_entity)
    except (ValueError, PeerIdInvalidError, ChannelInvalidError, ChannelPrivateError) as e:
        await event.reply(
            f"Could not find or access the specified chat/channel (`{entity_id_str}`). "
            "It might be invalid, private, or I might lack permissions."
        )
        return
    except Exception as e:
        await event.reply(f"An unexpected error occurred while fetching info for `{entity_id_str}`.")
        return

    msg = f"**Info for:** `{entity_id_str}`\n"
    msg += f"**Type:** `{type(entity).__name__}`\n"
    msg += f"**ID:** `{entity.id}`\n"

    if isinstance(entity, (types.Chat, types.Channel)):
        msg += f"**Title:** `{entity.title}`\n"
        if hasattr(entity, 'username') and entity.username:
            msg += f"**Username:** @{entity.username}\n"
        else:
            msg += f"**Username:** `None`\n"

        if hasattr(entity.photo, 'dc_id'):
            msg += f"**Photo DC:** `{entity.photo.dc_id}`\n"
        if hasattr(entity.photo, 'has_video'):
            msg += f"**Video PFP:** `{entity.photo.has_video}`\n"

        msg += f"**Scam:** `{getattr(entity, 'scam', 'N/A')}`\n"
        msg += f"**Restricted:** `{getattr(entity, 'restricted', 'N/A')}`\n"
        if getattr(entity, 'restriction_reason', None):
             msg += f"**Restriction Reason:** `{entity.restriction_reason}`\n"

        if isinstance(entity, types.Channel):
            msg += f"**Supergroup:** `{entity.megagroup}`\n"
            msg += f"**Broadcast Channel:** `{entity.broadcast}`\n"
            msg += f"**Verified:** `{entity.verified}`\n"
            msg += f"**Gigagroup:** `{getattr(entity, 'gigagroup', 'N/A')}`\n"
            msg += f"**Slowmode Enabled:** `{entity.slowmode_enabled}`\n"

        full_chat_info = None
        admin_list = []
        participant_count = "N/A"
        admin_count = "N/A"
        about = "N/A"

        try:
            if isinstance(entity, types.Channel):
                full_chat_info = await event.client(GetFullChannelRequest(channel=entity))
                about = full_chat_info.full_chat.about
                participant_count = getattr(full_chat_info.full_chat, 'participants_count', 'N/A')
            elif isinstance(entity, types.Chat):
                full_chat_info = await event.client(GetFullChatRequest(chat_id=entity.id))
                about = getattr(full_chat_info.full_chat, 'about', 'N/A')
                if hasattr(full_chat_info, 'users'):
                     participant_count = len(full_chat_info.users)

            try:
                admins = await event.client.get_participants(
                    entity, filter=ChannelParticipantsAdmins
                )
                admin_count = len(admins) if admins else 0 # Handle None case
                admin_list = [f"• [{admin.id}](tg://user?id={admin.id})" for admin in admins]
            except ChatAdminRequiredError:
                admin_list.append("_(Admin permissions required to list)_")
                admin_count = "N/A (No Perms)"
            except UserNotParticipantError:
                admin_list.append("_(Bot is not in this chat/channel)_")
                admin_count = "N/A (Not Participant)"
            except Exception as e:
                admin_list.append("_(Could not retrieve admin list)_")
                admin_count = "N/A (Error)"


            msg += "\n**Stats:**\n"
            msg += f"`Participants:` `{participant_count}`\n"
            msg += f"`Admins:` `{admin_count}`\n"

            if admin_list:
                msg += "\n**Admins List:**"
                msg += "\n" + "\n".join(admin_list) # Join list items with newlines

            msg += f"\n\n**Description:**\n`{about}`"

        except (ChatAdminRequiredError, UserNotParticipantError) as e:
             msg += "\n\n**(Could not retrieve full details like description or participant counts due to permissions or bot not being a participant)**"
        except Exception as e:
             msg += "\n\n**(An error occurred while retrieving full details)**"

    else:
        msg += "\n**(Unsupported entity type)**"

    await event.reply(msg, link_preview=False)

def gifid(update: Update, context: CallbackContext):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.animation:
        update.effective_message.reply_text(
            f"Gif ID:\n<code>{msg.reply_to_message.animation.file_id}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        update.effective_message.reply_text("Please reply to a gif to get its ID.")


def info(update: Update, context: CallbackContext):
    bot, args = context.bot, context.args
    message = update.effective_message
    chat = update.effective_chat
    user_id = extract_user(update.effective_message, args)

    if user_id and int(user_id) != 777000 and int(user_id) != 1087968824:
        user = bot.get_chat(user_id)

    elif user_id and int(user_id) == 777000:
        message.reply_text(
            "This is Telegram. Unless you manually entered this reserved account's ID, it is likely a old broadcast from a linked channel."
        )
        return
        
    elif user_id and int(user_id) == 1087968824:
        message.reply_text(
            "This is Group Anonymous Bot. Unless you manually entered this reserved account's ID, it is likely a broadcast from a linked channel or anonymously sent message."
        )
        return

    elif not message.reply_to_message and not args:
        user = (
            message.sender_chat
            if message.sender_chat is not None
            else message.from_user
        )

    elif not message.reply_to_message and (
        not args
        or (
            len(args) >= 1
            and not args[0].startswith("@")
            and not args[0].isdigit()
            and not message.parse_entities([MessageEntity.TEXT_MENTION])
        )
    ):
        delmsg = message.reply_text("I can't extract a user from this.")

        cleartime = get_clearcmd(chat.id, "info")
        
        if cleartime:
            context.dispatcher.run_async(delete, delmsg, cleartime.time)

        return

    else:
        return
        
    rep = message.reply_text("<code>Appraising...</code>", parse_mode=ParseMode.HTML)  
     
    if hasattr(user, 'type') and user.type != "private":
        text = (
            f"<b>Chat Info: </b>"
            f"\nID: <code>{user.id}</code>"
            f"\nTitle: {user.title}"
        )
        if user.username:
            text += f"\nUsername: @{html.escape(user.username)}"
        text += f"\nChat Type: {user.type.capitalize()}"
        
        if INFOPIC:
            try:
                profile = bot.getChat(user.id).photo
                _file = bot.get_file(profile["big_file_id"])
                _file.download(f"{user.id}.png")

                delmsg = message.reply_document(
                    document=open(f"{user.id}.png", "rb"),
                    caption=(text),
                    parse_mode=ParseMode.HTML,
                )

                os.remove(f"{user.id}.png")
            # Incase chat don't have profile pic, send normal text
            except:
                delmsg = message.reply_text(
                    text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                )

        else:
            delmsg = message.reply_text(
                text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )

    else:
        text = (
            f"<b>User info:</b>\n"
            f"ID: <code>{user.id}</code>\n"
            f"First Name: {mention_html(user.id, user.first_name or 'None')}"
        )

        if user.last_name:
            text += f"\nLast Name: {html.escape(user.last_name)}"

        if user.username:
            text += f"\nUsername: @{html.escape(user.username)}"

        text += f"\nPermalink: {mention_html(user.id, 'link')}"

        if chat.type != "private" and user_id != bot.id:
            _stext = "\nPresence: <code>{}</code>"

            afk_st = is_afk(user.id)
            if afk_st:
                text += _stext.format("AFK")
            else:
                status = bot.get_chat_member(chat.id, user.id).status
                if status:
                    if status == "left":
                        text += _stext.format("Not here")
                    if status == "kicked":
                        text += _stext.format("Banned")
                    elif status == "member":
                        text += _stext.format("Detected")
                    elif status in {"administrator", "creator"}:
                        text += _stext.format("Admin")

        try:
            spamwtc = sw.get_ban(int(user.id))
            if spamwtc:
                text += "\n\n<b>This person is Spamwatched!</b>"
                text += f"\nReason: <pre>{spamwtc.reason}</pre>"
                text += "\nAppeal at @SpamWatchSupport"
            else:
                pass
        except:
            pass  # don't crash if api is down somehow...

        disaster_level_present = False

        if user.id == OWNER_ID:
            text += "\n\nUser level: <b>god</b>"
            disaster_level_present = True
        elif user.id in DEV_USERS:
            text += "\n\nUser level: <b>developer</b>"
            disaster_level_present = True
        elif user.id in SUDO_USERS:
            text += "\n\nUser level: <b>sudo</b>"
            disaster_level_present = True
        elif user.id in SUPPORT_USERS:
            text += "\n\nUser level: <b>support</b>"
            disaster_level_present = True
        elif user.id in WHITELIST_USERS:
            text += "\n\nUser level: <b>whitelist</b>"
            disaster_level_present = True

        # if disaster_level_present:
        #     text += ' [<a href="https://t.me/OnePunchUpdates/155">?</a>]'.format(
        #         bot.username)

        try:
            user_member = chat.get_member(user.id)
            if user_member.status == "administrator":
                result = requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/getChatMember?chat_id={chat.id}&user_id={user.id}"
                )
                result = result.json()["result"]
                if "custom_title" in result.keys():
                    custom_title = result["custom_title"]
                    text += f"\n\nTitle:\n<b>{custom_title}</b>"
        except BadRequest:
            pass

        for mod in USER_INFO:
            try:
                mod_info = mod.__user_info__(user.id).strip()
            except TypeError:
                mod_info = mod.__user_info__(user.id, chat.id).strip()
            if mod_info:
                text += "\n\n" + mod_info

        text += "\n\n" + biome(user.id)

        if INFOPIC:
            try:
                profile = context.bot.get_user_profile_photos(user.id).photos[0][-1]
                _file = bot.get_file(profile["file_id"])
                _file.download(f"{user.id}.png")

                delmsg = message.reply_document(
                    document=open(f"{user.id}.png", "rb"),
                    caption=(text),
                    parse_mode=ParseMode.HTML,
                )

                os.remove(f"{user.id}.png")
            # Incase user don't have profile pic, send normal text
            except IndexError:
                delmsg = message.reply_text(
                    text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                )

        else:
            delmsg = message.reply_text(
                text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )    
    
    rep.delete()
              
    cleartime = get_clearcmd(chat.id, "info")
        
    if cleartime:
        context.dispatcher.run_async(delete, delmsg, cleartime.time)

def about_me(update: Update, context: CallbackContext):
    bot, args = context.bot, context.args
    message = update.effective_message
    user_id = extract_user(message, args)

    if user_id:
        user = bot.get_chat(user_id)
    else:
        user = message.from_user

    info = sql.get_user_me_info(user.id)

    if info:
        update.effective_message.reply_text(
            f"*{user.first_name}*:\n{escape_markdown(info)}",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    elif message.reply_to_message:
        username = message.reply_to_message.from_user.first_name
        update.effective_message.reply_text(
            f"{username} hasn't set an info message about themselves yet!"
        )
    else:
        update.effective_message.reply_text("There isnt one, use /setme to set one.")


def set_about_me(update: Update, context: CallbackContext):
    message = update.effective_message
    user_id = message.from_user.id
    if user_id in [777000, 1087968824]:
        message.reply_text("Error! Unauthorized")
        return
    bot = context.bot
    if message.reply_to_message:
        repl_message = message.reply_to_message
        repl_user_id = repl_message.from_user.id
        if repl_user_id in [bot.id, 777000, 1087968824] and (user_id in DEV_USERS):
            user_id = repl_user_id
    text = message.text
    info = text.split(None, 1)
    if len(info) == 2:
        if len(info[1]) < MAX_MESSAGE_LENGTH // 4:
            sql.set_user_me_info(user_id, info[1])
            if user_id in [777000, 1087968824]:
                message.reply_text("Authorized...Information updated!")
            elif user_id == bot.id:
                message.reply_text("I have updated my info with the one you provided!")
            else:
                message.reply_text("Information updated!")
        else:
            message.reply_text(
                "The info needs to be under {} characters! You have {}.".format(
                    MAX_MESSAGE_LENGTH // 4, len(info[1])
                )
            )


@sudo_plus
def stats(update: Update, context: CallbackContext):
    stats = "<b>📊 Current stats:</b>\n" + "\n".join([mod.__stats__() for mod in STATS])
    result = re.sub(r"(\d+)", r"<code>\1</code>", stats)
    update.effective_message.reply_text(result, parse_mode=ParseMode.HTML)


def about_bio(update: Update, context: CallbackContext):
    bot, args = context.bot, context.args
    message = update.effective_message

    user_id = extract_user(message, args)
    if user_id:
        user = bot.get_chat(user_id)
    else:
        user = message.from_user

    info = sql.get_user_bio(user.id)

    if info:
        update.effective_message.reply_text(
            "*{}*:\n{}".format(user.first_name, escape_markdown(info)),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    elif message.reply_to_message:
        username = user.first_name
        update.effective_message.reply_text(
            f"{username} hasn't had a message set about themselves yet!\nSet one using /setbio"
        )
    else:
        update.effective_message.reply_text(
            "You haven't had a bio set about yourself yet!"
        )


def set_about_bio(update: Update, context: CallbackContext):
    message = update.effective_message
    sender_id = update.effective_user.id
    bot = context.bot

    if message.reply_to_message:
        repl_message = message.reply_to_message
        user_id = repl_message.from_user.id

        if user_id == message.from_user.id:
            message.reply_text(
                "Ha, you can't set your own bio! You're at the mercy of others here..."
            )
            return

        if user_id in [777000, 1087968824] and sender_id not in DEV_USERS:
            message.reply_text("You are not authorised")
            return

        if user_id == bot.id and sender_id not in DEV_USERS:
            message.reply_text(
                "Erm... yeah, I only trust developer users to set my bio."
            )
            return

        text = message.text
        bio = text.split(
            None, 1
        )  # use python's maxsplit to only remove the cmd, hence keeping newlines.

        if len(bio) == 2:
            if len(bio[1]) < MAX_MESSAGE_LENGTH // 4:
                sql.set_user_bio(user_id, bio[1])
                message.reply_text(
                    "Updated {}'s bio!".format(repl_message.from_user.first_name)
                )
            else:
                message.reply_text(
                    "Bio needs to be under {} characters! You tried to set {}.".format(
                        MAX_MESSAGE_LENGTH // 4, len(bio[1])
                    )
                )
    else:
        message.reply_text("Reply to someone to set their bio!")


def gdpr(update: Update, context: CallbackContext):
    update.effective_message.reply_text("Deleting identifiable data...")
    for mod in GDPR:
        mod.__gdpr__(update.effective_user.id)

    update.effective_message.reply_text("Your personal data has been deleted.\n\nNote that this will not unban "
                                        "you from any chats, as that is telegram data, not AstrakoBot data. "
                                        "Flooding, warns, and gbans are also preserved, as of "
                                        "[this](https://ico.org.uk/for-organisations/guide-to-the-general-data-protection-regulation-gdpr/individual-rights/right-to-erasure/), "
                                        "which clearly states that the right to erasure does not apply "
                                        "\"for the performance of a task carried out in the public interest\", as is "
                                        "the case for the aforementioned pieces of data.",
                                        parse_mode=ParseMode.MARKDOWN)


def biome(user_id):
    bio = html.escape(sql.get_user_bio(user_id) or "")
    me = html.escape(sql.get_user_me_info(user_id) or "")
    result = ""
    if me:
        result += f"<b>About user:</b>\n{me}\n"
    if bio:
        result += f"<b>What others say:</b>\n{bio}\n"
    result = result.strip("\n")
    return result


def __gdpr__(user_id):
    sql.clear_user_info(user_id)
    sql.clear_user_bio(user_id)


__help__ = """
*ID:*
 • `/id`*:* get the current group id. If used by replying to a message, gets that user's id.
 • `/gifid`*:* reply to a gif to me to tell you its file ID.

*Self addded information:* 
 • `/setme <text>`*:* will set your info
 • `/me`*:* will get your or another user's info.
Examples:
 `/setme I am a wolf.`
 `/me @username(defaults to yours if no user specified)`

*Information others add on you:* 
 • `/bio`*:* will get your or another user's bio. This cannot be set by yourself.
• `/setbio <text>`*:* while replying, will save another user's bio 
Examples:
 `/bio @username(defaults to yours if not specified).`
 `/setbio This user is a wolf` (reply to the user)

*Overall Information about you:*
 • `/info`*:* get information about a user.

*Guide to the General Data Protection Regulation (GDPR):*
 • `/gdpr`*:* deletes your information from the bot's database. Private chats only.
"""

SET_BIO_HANDLER = DisableAbleCommandHandler("setbio", set_about_bio, run_async=True)
GET_BIO_HANDLER = DisableAbleCommandHandler("bio", about_bio, run_async=True)

STATS_HANDLER = CommandHandler("stats", stats, run_async=True)
ID_HANDLER = DisableAbleCommandHandler("id", get_id, run_async=True)
GIFID_HANDLER = DisableAbleCommandHandler("gifid", gifid, run_async=True)
INFO_HANDLER = DisableAbleCommandHandler(("info", "book"), info, run_async=True)
GDPR_HANDLER = CommandHandler("gdpr", gdpr, filters=Filters.chat_type.private, run_async=True)

SET_ABOUT_HANDLER = DisableAbleCommandHandler("setme", set_about_me, run_async=True)
GET_ABOUT_HANDLER = DisableAbleCommandHandler("me", about_me, run_async=True)

dispatcher.add_handler(STATS_HANDLER)
dispatcher.add_handler(ID_HANDLER)
dispatcher.add_handler(GIFID_HANDLER)
dispatcher.add_handler(INFO_HANDLER)
dispatcher.add_handler(GDPR_HANDLER)
dispatcher.add_handler(SET_BIO_HANDLER)
dispatcher.add_handler(GET_BIO_HANDLER)
dispatcher.add_handler(SET_ABOUT_HANDLER)
dispatcher.add_handler(GET_ABOUT_HANDLER)

__mod_name__ = "Info"
__command_list__ = ["setbio", "bio", "setme", "me", "info", "gprd"]
__handlers__ = [
    ID_HANDLER,
    GIFID_HANDLER,
    INFO_HANDLER,
    GDPR_HANDLER,
    SET_BIO_HANDLER,
    GET_BIO_HANDLER,
    SET_ABOUT_HANDLER,
    GET_ABOUT_HANDLER,
    STATS_HANDLER,
]

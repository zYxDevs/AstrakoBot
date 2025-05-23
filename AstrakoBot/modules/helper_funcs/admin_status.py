from threading import RLock

from cachetools import TTLCache

from telegram import Chat, ChatMember, TelegramError, Update
from telegram.ext import CallbackContext, ChatMemberHandler
from telegram.error import Unauthorized

from AstrakoBot import SUDO_USERS, dispatcher

BOT_ADMIN_CACHE = TTLCache(maxsize = 512, ttl = 60 * 30)
USER_ADMIN_CACHE = TTLCache(maxsize = 512, ttl = 60 * 30)
RLOCK = RLock()


def get_bot_member(chat_id: int) -> ChatMember:
	try:
		return BOT_ADMIN_CACHE[chat_id]
	except KeyError:
		try:
			mem = dispatcher.bot.getChatMember(chat_id, dispatcher.bot.id)
			BOT_ADMIN_CACHE[chat_id] = mem
			return mem
		except:
			bot_user = dispatcher.bot.get_me()
			ghost = ChatMember(
				user=bot_user,
				status='member',
				can_be_edited=False,
				is_anonymous=False,
				can_manage_chat=False,
				can_delete_messages=False,
				can_manage_video_chats=False,
				can_restrict_members=False,
				can_promote_members=False,
				can_change_info=False,
				can_invite_users=False,
				can_post_messages=False,
				can_edit_messages=False,
				can_pin_messages=False,
				can_manage_topics=False,
				can_send_messages=False,
			)
			return ghost


def user_is_admin(chat: Chat, user_id: int) -> bool:
	if chat.type == "private" or user_id in SUDO_USERS:
		return True

	member: ChatMember = get_mem_from_cache(user_id, chat.id)

	if not member:  # not in cache so not an admin
		return False

	return member.status in ["administrator", "creator"]  # check if user is admin


def get_mem_from_cache(user_id: int, chat_id: int) -> ChatMember:
	with RLOCK:
		try:
			for i in USER_ADMIN_CACHE[chat_id]:
				if i.user.id == user_id:
					return i

		except KeyError:
			try:
				admins = dispatcher.bot.getChatAdministrators(chat_id)
			except Unauthorized:
				return None
			USER_ADMIN_CACHE[chat_id] = admins
			for i in admins:
				if i.user.id == user_id:
					return i


def admincacheupdates(update: Update, _: CallbackContext):
	try:
		oldstat = update.chat_member.old_chat_member.status
		newstat = update.chat_member.new_chat_member.status
	except AttributeError:
		return
	if (
		oldstat == "administrator"
		and newstat != "administrator"
		or oldstat != "administrator"
		and newstat == "administrator"
	):

		USER_ADMIN_CACHE[update.effective_chat.id] = update.effective_chat.get_administrators()


def botstatchanged(update: Update, _: CallbackContext):
	if update.effective_chat.type != "private":
		try:
			BOT_ADMIN_CACHE[update.effective_chat.id] = update.effective_chat.get_member(dispatcher.bot.id)
		except TelegramError:
			pass


dispatcher.add_handler(ChatMemberHandler(botstatchanged, ChatMemberHandler.MY_CHAT_MEMBER, run_async=True), group=-20)
dispatcher.add_handler(ChatMemberHandler(admincacheupdates, ChatMemberHandler.CHAT_MEMBER, run_async=True), group=-21)

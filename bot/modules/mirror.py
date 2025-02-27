import requests

from re import match, search, split as resplit
from time import sleep, time
from os import path as ospath, remove as osremove, listdir, walk
from shutil import rmtree
from threading import Thread
from subprocess import run as srun
from pathlib import PurePath
from html import escape
from urllib.parse import quote
from telegram.ext import CommandHandler
from telegram import InlineKeyboardMarkup, ParseMode, InlineKeyboardButton

from bot import bot, Interval, OWNER_ID, INDEX_URL, BUTTON_FOUR_NAME, BUTTON_FOUR_URL, BUTTON_FIVE_NAME, BUTTON_FIVE_URL, \
                 BLOCK_MEGA_FOLDER, BLOCK_MEGA_LINKS, VIEW_LINK, aria2, QB_SEED, \
                dispatcher, DOWNLOAD_DIR, download_dict, download_dict_lock, TG_SPLIT_SIZE, LOGGER, \
                MIRROR_LOGS, BOT_PM, CHANNEL_USERNAME, LEECH_ENABLED, AUTO_DELETE_UPLOAD_MESSAGE_DURATION, FSUB, \
                FSUB_CHANNEL_ID, LEECH_LOG, SOURCE_LINK, LEECH_LOG_ALT, MEGAREST, LINK_LOGS
from bot.helper.ext_utils.bot_utils import is_url, is_magnet, is_gdtot_link, is_mega_link, is_gdrive_link, get_content_type, get_mega_link_type
from bot.helper.ext_utils.fs_utils import get_base_name, get_path_size, split as fssplit, clean_download
from bot.helper.ext_utils.shortenurl import short_url
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException, NotSupportedExtractionArchive
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.mega_downloader import add_mega_download
from bot.helper.mirror_utils.download_utils.mega_download import MegaDownloadeHelper
from bot.helper.mirror_utils.download_utils.gd_downloader import add_gd_download
from bot.helper.mirror_utils.download_utils.qbit_downloader import add_qb_torrent
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloadHelper
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.mirror_utils.status_utils.split_status import SplitStatus
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus
from bot.helper.mirror_utils.status_utils.tg_upload_status import TgUploadStatus
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.upload_utils.pyrogramEngine import TgUploader
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, sendMarkup, delete_all_messages, update_all_messages, auto_delete_message, auto_delete_upload_message, sendStatusMessage
from bot.helper.telegram_helper.button_build import ButtonMaker


class MirrorListener:
    def __init__(self, bot, update, isZip=False, extract=False, isQbit=False, isLeech=False, pswd=None, tag=None):
        self.bot = bot
        self.update = update
        self.message = update.message
        self.uid = self.message.message_id
        self.extract = extract
        self.isZip = isZip
        self.isQbit = isQbit
        self.isLeech = isLeech
        self.pswd = pswd
        self.tag = tag
        self.user_id = self.message.from_user.id
        self.__chat_id = self.message.chat.id

    def clean(self):
        try:
            aria2.purge()
            Interval[0].cancel()
            del Interval[0]
            delete_all_messages()
        except IndexError:
            pass
    def onDownloadStarted(self):
        pass

    def onDownloadProgress(self):
        # We are handling this on our own!
        pass
    def onDownloadComplete(self):
        with download_dict_lock:
            LOGGER.info(f"Download completed: {download_dict[self.uid].name()}")
            download = download_dict[self.uid]
            name = str(download.name()).replace('/', '')
            gid = download.gid()
            size = download.size_raw()
            if name == "None" or self.isQbit or not ospath.exists(f'{DOWNLOAD_DIR}{self.uid}/{name}'):
                name = listdir(f'{DOWNLOAD_DIR}{self.uid}')[-1]
            m_path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        if self.isZip:
            try:
                with download_dict_lock:
                    download_dict[self.uid] = ZipStatus(name, m_path, size)
                path = m_path + ".zip"
                LOGGER.info(f'Zip: orig_path: {m_path}, zip_path: {path}')
                if self.pswd is not None:
                    if self.isLeech and int(size) > TG_SPLIT_SIZE:
                        srun(["7z", f"-v{TG_SPLIT_SIZE}b", "a", "-mx=0", f"-p{self.pswd}", path, m_path])
                    else:
                        srun(["7z", "a", "-mx=0", f"-p{self.pswd}", path, m_path])
                elif self.isLeech and int(size) > TG_SPLIT_SIZE:
                    srun(["7z", f"-v{TG_SPLIT_SIZE}b", "a", "-mx=0", path, m_path])
                else:
                    srun(["7z", "a", "-mx=0", path, m_path])
            except FileNotFoundError:
                LOGGER.info('File to archive not found!')
                self.onUploadError('Internal error occurred!!')
                return
            if not self.isQbit or not QB_SEED or self.isLeech:
                try:
                    rmtree(m_path)
                except:
                    osremove(m_path)
        elif self.extract:
            try:
                if ospath.isfile(m_path):
                    path = get_base_name(m_path)
                LOGGER.info(f"Extracting: {name}")
                with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, m_path, size)
                if ospath.isdir(m_path):
                    for dirpath, subdir, files in walk(m_path, topdown=False):
                        for file_ in files:
                            if file_.endswith(".zip") or search(r'\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$', file_) \
                               or (file_.endswith(".rar") and not search(r'\.part\d+\.rar$', file_)):
                                m_path = ospath.join(dirpath, file_)
                                if self.pswd is not None:
                                    result = srun(["7z", "x", f"-p{self.pswd}", m_path, f"-o{dirpath}", "-aot"])
                                else:
                                    result = srun(["7z", "x", m_path, f"-o{dirpath}", "-aot"])
                                if result.returncode != 0:
                                    LOGGER.error('Unable to extract archive!')
                        for file_ in files:
                            if file_.endswith((".rar", ".zip")) or search(r'\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$', file_):
                                del_path = ospath.join(dirpath, file_)
                                osremove(del_path)
                    path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
                else:
                    if self.pswd is not None:
                        result = srun(["bash", "pextract", m_path, self.pswd])
                    else:
                        result = srun(["bash", "extract", m_path])
                    if result.returncode == 0:
                        LOGGER.info(f"Extracted Path: {path}")
                        osremove(m_path)
                    else:
                        LOGGER.error('Unable to extract archive! Uploading anyway')
                        path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        else:
            path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        up_name = PurePath(path).name
        up_path = f'{DOWNLOAD_DIR}{self.uid}/{up_name}'
        if self.isLeech and not self.isZip:
            checked = False
            for dirpath, subdir, files in walk(f'{DOWNLOAD_DIR}{self.uid}', topdown=False):
                for file_ in files:
                    f_path = ospath.join(dirpath, file_)
                    f_size = ospath.getsize(f_path)
                    if int(f_size) > TG_SPLIT_SIZE:
                        if not checked:
                            checked = True
                            with download_dict_lock:
                                download_dict[self.uid] = SplitStatus(up_name, up_path, size)
                            LOGGER.info(f"Splitting: {up_name}")
                        fssplit(f_path, f_size, file_, dirpath, TG_SPLIT_SIZE)
                        osremove(f_path)
        if self.isLeech:
            size = get_path_size(f'{DOWNLOAD_DIR}{self.uid}')
            LOGGER.info(f"Leech Name: {up_name}")
            tg = TgUploader(up_name, self)
            tg_upload_status = TgUploadStatus(tg, size, gid, self)
            with download_dict_lock:
                download_dict[self.uid] = tg_upload_status
            update_all_messages()
            tg.upload()
        else:
            size = get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name}")
            drive = GoogleDriveHelper(up_name, self)
            upload_status = UploadStatus(drive, size, gid, self)
            with download_dict_lock:
                download_dict[self.uid] = upload_status
            update_all_messages()
            drive.upload(up_name)

    def onDownloadError(self, error):
        reply_to = self.message.reply_to_message
        if reply_to is not None:
            reply_to.delete()
        error = error.replace('<', ' ').replace('>', ' ')
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                clean_download(download.path())
            except Exception as e:
                LOGGER.error(str(e))
            count = len(download_dict)
        msg = f"{self.tag} your download has been stopped due to: {error}"
        msg = sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()
        Thread(target=auto_delete_message, args=(bot, self.message, msg)).start()

    def onUploadComplete(self, link: str, size, files, folders, typ, name: str):
        uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        chat_id = str(LEECH_LOG)[5:][:-1]
        buttons = ButtonMaker()
        # this is inspired by def mirror to get the link from message
        mesg = self.message.text.split('\n')
        message_args = mesg[0].split(' ', maxsplit=1)
        reply_to = self.message.reply_to_message
        slmsg = f"Added by: {uname} \nUser ID: <code>{self.user_id}</code>\n\n"
        if LINK_LOGS:
            try:
                source_link = message_args[1]
                for link_log in LINK_LOGS:
                    bot.sendMessage(link_log, text=slmsg + source_link, parse_mode=ParseMode.HTML )
            except IndexError:
                pass
            if reply_to is not None:
                try:
                    reply_text = reply_to.text
                    if is_url(reply_text):
                        source_link = reply_text.strip()
                        for link_log in LINK_LOGS:
                            bot.sendMessage(chat_id=link_log, text=slmsg + source_link, parse_mode=ParseMode.HTML )
                except TypeError:
                    pass
            '''
        msg_id = 
        link_id = str(LINK_LOGS)[5:][:-1]
        S_link =  f"https://t.me/c/{link_id}/{msg_id}"
            '''
        msg = f'<b>Name: </b><code>{name.replace("<", "")}</code>\n\n<b>Size: </b>{size}'
        if AUTO_DELETE_UPLOAD_MESSAGE_DURATION != -1:
            reply_to = self.message.reply_to_message
            if reply_to is not None:
                reply_to.delete()
            auto_delete_message = int(AUTO_DELETE_UPLOAD_MESSAGE_DURATION / 60)
            if self.message.chat.type == 'private':
                warnmsg = ''
            else:
                warnmsg = f'\n<b>This message will be deleted in <i>{auto_delete_message} minutes</i> from this group.</b>\n'
        else:
            warnmsg = ''
        if BOT_PM and self.message.chat.type != 'private':
            pmwarn = f"\n<b>I have sent files in PM.</b>\n"
            pmwarn_mirror = f"\n<b>I have sent links in PM.</b>\n"
        elif self.message.chat.type == 'private':
            pmwarn = ''
            pmwarn_mirror = ''
        else:
            pmwarn = ''
            pmwarn_mirror = ''
        logwarn = f"\n<b>I have sent files in Log Channel.</b>\n"
        if self.isLeech:
            count = len(files)
            msg += f'\n<b>Total Files: </b>{count}'
            if typ != 0:
                msg += f'\n<b>Corrupted Files: </b>{typ}'
            msg += f'\n<b>#Leeched By: </b>{self.tag}\n'
            if BOT_PM:
                message = sendMessage(msg + pmwarn + warnmsg, self.bot, self.update)
                Thread(target=auto_delete_upload_message, args=(bot, self.message, message)).start()

            if MIRROR_LOGS:
                for i in MIRROR_LOGS:
                    """
                    if SOURCE_LINK is True:
                        buttons.buildbutton("🔗 Source Link", S_link)
                    """
                    indexmsg = ''
                    for index, item in enumerate(list(files), start=1):
                        msg_id = files[item]
                        link = f"https://t.me/c/{chat_id}/{msg_id}"
                        indexmsg += f"{index}. <a href='{link}'>{item}</a>\n"
                        if len(indexmsg.encode('utf-8') + msg.encode('utf-8')) > 4000:
                            sleep(1.5)
                            bot.sendMessage(chat_id=i, text=msg + indexmsg,
                                            reply_markup=InlineKeyboardMarkup(buttons.build_menu(2)),
                                            parse_mode=ParseMode.HTML)
                            indexmsg = ''
                    if indexmsg != '':
                        sleep(1.5)
                        bot.sendMessage(chat_id=i, text=msg + indexmsg,
                                        reply_markup=InlineKeyboardMarkup(buttons.build_menu(2)),
                                        parse_mode=ParseMode.HTML)


            else:
                fmsg = '\n\n'
                for index, item in enumerate(list(files), start=1):
                    msg_id = files[item]
                    link = f"https://t.me/c/{chat_id}/{msg_id}"
                    fmsg += f"{index}. <a href='{link}'>{item}</a>\n"
                    if len(fmsg.encode('utf-8') + msg.encode('utf-8')) > 4000:
                        sendMessage(msg + fmsg + logwarn, self.bot, self.update)
                        sleep(1.5)
                        fmsg = ''
                if fmsg != '':
                    sendMessage(msg + fmsg, self.bot, self.update)

            try:
                clean_download(f'{DOWNLOAD_DIR}{self.uid}')
            except FileNotFoundError:
                pass
            with download_dict_lock:
                del download_dict[self.uid]
                dcount = len(download_dict)
            if dcount == 0:
                self.clean()
            else:
                update_all_messages()
        else:
            msg += f'\n\n<b>Type: </b>{typ}'
            if ospath.isdir(f'{DOWNLOAD_DIR}{self.uid}/{name}'):
                msg += f'\n<b>SubFolders: </b>{folders}'
                msg += f'\n<b>Files: </b>{files}'
            link = short_url(link)
            buttons.buildbutton("☁️ Drive Link", link)
            LOGGER.info(f'Done Uploading {name}')
            if INDEX_URL is not None:
                url_path = requests.utils.quote(f'{name}')
                share_url = f'{INDEX_URL}/{url_path}'
                if ospath.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{name}'):
                    share_url += '/'
                    share_url = short_url(share_url)
                    buttons.buildbutton("⚡ Index Link", share_url)
                else:
                    share_url = short_url(share_url)
                    buttons.buildbutton("⚡ Index Link", share_url)
                    if VIEW_LINK:
                        share_urls = f'{INDEX_URL}/{url_path}?a=view'
                        share_urls = short_url(share_urls)
                        buttons.buildbutton("🌐 View Link", share_urls)
            if BUTTON_FOUR_NAME is not None and BUTTON_FOUR_URL is not None:
                buttons.buildbutton(f"{BUTTON_FOUR_NAME}", f"{BUTTON_FOUR_URL}")
            if BUTTON_FIVE_NAME is not None and BUTTON_FIVE_URL is not None:
                buttons.buildbutton(f"{BUTTON_FIVE_NAME}", f"{BUTTON_FIVE_URL}")
            """
            if SOURCE_LINK is True:
                buttons.buildbutton(f"🔗 Source Link", S_link)
            """
            uploader = f'\n\n<b>#Uploaded By: </b>{self.tag}\n'
            if MIRROR_LOGS:
                try:
                    for i in MIRROR_LOGS:
                        bot.sendMessage(chat_id=i, text=msg + uploader,
                                    reply_markup=InlineKeyboardMarkup(buttons.build_menu(2)),
                                    parse_mode=ParseMode.HTML)
                except Exception as e:
                    LOGGER.warning(e)

                if BOT_PM and self.message.chat.type != 'private':
                    try:
                        bot.sendMessage(chat_id=self.user_id, text=msg,
                                    reply_markup=InlineKeyboardMarkup(buttons.build_menu(2)),
                                    parse_mode=ParseMode.HTML)
                    except Exception as e:
                        LOGGER.warning(e)
                        return
            if self.isQbit and QB_SEED and not self.extract:
                if self.isZip:
                    try:
                        osremove(f'{DOWNLOAD_DIR}{self.uid}/{name}')
                    except:
                        pass
                msg = sendMarkup(msg + uploader + pmwarn_mirror + warnmsg, self.bot, self.update, InlineKeyboardMarkup(buttons.build_menu(2)))
                Thread(target=auto_delete_upload_message, args=(bot, self.message, msg)).start()
                return
            else:
                try:
                    clean_download(f'{DOWNLOAD_DIR}{self.uid}')
                except FileNotFoundError:
                    pass
                with download_dict_lock:
                    del download_dict[self.uid]
                    count = len(download_dict)
                msg = sendMarkup(msg + uploader + pmwarn_mirror + warnmsg, self.bot, self.update, InlineKeyboardMarkup(buttons.build_menu(2)))
                if count == 0:
                    self.clean()
                else:
                    update_all_messages()
                Thread(target=auto_delete_upload_message, args=(bot, self.message, msg)).start()

    def onUploadError(self, error):
        reply_to = self.message.reply_to_message
        if reply_to is not None:
            reply_to.delete()
        e_str = error.replace('<', '').replace('>', '')
        with download_dict_lock:
            try:
                clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.message.message_id]
            count = len(download_dict)
        msg = sendMessage(f"{self.tag} {e_str}", self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()
        Thread(target=auto_delete_message, args=(bot, self.message, msg)).start()

def _mirror(bot, update, isZip=False, extract=False, isQbit=False, isLeech=False, pswd=None, multi=0):
    uname = f'<a href="tg://user?id={update.message.from_user.id}">{update.message.from_user.first_name}</a>'
    if FSUB:
        try:
            user = bot.get_chat_member(f"{FSUB_CHANNEL_ID}", update.message.from_user.id)
            LOGGER.error(user.status)
            if user.status not in ('member', 'creator', 'administrator'):
                buttons = ButtonMaker()
                buttons.buildbutton("Click Here To Join Updates Channel", f"https://t.me/{CHANNEL_USERNAME}")
                reply_markup = InlineKeyboardMarkup(buttons.build_menu(1))
                message = sendMarkup(
                    str(f"<b>Dear {uname}️ You haven't join our Updates Channel yet.</b>\n\nKindly Join @{CHANNEL_USERNAME} To Use Bots. "),
                    bot, update, reply_markup)
                Thread(target=auto_delete_upload_message, args=(bot, update.message, message)).start()
                return
        except:
            pass
    if BOT_PM:
        try:
            msg1 = f'Added your Requested link to Download\n'
            send = bot.sendMessage(update.message.from_user.id, text=msg1, )
            send.delete()
        except Exception as e:
            LOGGER.warning(e)
            bot_d = bot.get_me()
            b_uname = bot_d.username
            uname = f'<a href="tg://user?id={update.message.from_user.id}">{update.message.from_user.first_name}</a>'
            channel = CHANNEL_USERNAME
            botstart = f"http://t.me/{b_uname}"
            keyboard = [
                [InlineKeyboardButton("Click Here to Start Me", url=f"{botstart}")]]
            message = sendMarkup(
                f"Dear {uname},\n\n<b>I found that you haven't started me in PM (Private Chat) yet.</b>\n\nFrom now on i will give link and leeched files in PM and log channel only",
                bot, update, reply_markup=InlineKeyboardMarkup(keyboard))
            Thread(target=auto_delete_message, args=(bot, update.message, message)).start()
            return
    mesg = update.message.text.split('\n')
    message_args = mesg[0].split(' ', maxsplit=1)
    name_args = mesg[0].split('|', maxsplit=1)
    qbitsel = False
    is_gdtot = False
    try:
        link = message_args[1]
        if link.startswith("s ") or link == "s":
            qbitsel = True
            message_args = mesg[0].split(' ', maxsplit=2)
            link = message_args[2].strip()
        elif link.isdigit():
            multi = int(link)
            raise IndexError
        if link.startswith(("|", "pswd: ")):
            raise IndexError
    except:
        link = ''
    try:
        name = name_args[1]
        name = name.split(' pswd: ')[0]
        name = name.strip()
    except:
        name = ''
    link = resplit(r"pswd:| \|", link)[0]
    link = link.strip()
    pswdMsg = mesg[0].split(' pswd: ')
    if len(pswdMsg) > 1:
        pswd = pswdMsg[1]

    if update.message.from_user.username:
        tag = f"@{update.message.from_user.username}"
    else:
        tag = update.message.from_user.mention_html(update.message.from_user.first_name)

    reply_to = update.message.reply_to_message
    if reply_to is not None:
        file = None
        media_array = [reply_to.document, reply_to.video, reply_to.audio]
        for i in media_array:
            if i is not None:
                file = i
                break

        if not reply_to.from_user.is_bot:
            if reply_to.from_user.username:
                tag = f"@{reply_to.from_user.username}"
            else:
                tag = reply_to.from_user.mention_html(reply_to.from_user.first_name)

        if (
            not is_url(link)
            and not is_magnet(link)
            or len(link) == 0
        ):

            if file is None:
                reply_text = reply_to.text
                if is_url(reply_text) or is_magnet(reply_text):
                    link = reply_text.strip()
            elif isQbit:
                file_name = str(time()).replace(".", "") + ".torrent"
                link = file.get_file().download(custom_path=file_name)
            elif file.mime_type != "application/x-bittorrent":
                listener = MirrorListener(bot, update, isZip, extract, isQbit, isLeech, pswd, tag)
                tg_downloader = TelegramDownloadHelper(listener)
                ms = update.message
                tg_downloader.add_download(ms, f'{DOWNLOAD_DIR}{listener.uid}/', name)
                if multi > 1:
                    sleep(3)
                    nextmsg = type('nextmsg', (object, ), {'chat_id': message.chat_id, 'message_id': message.reply_to_message.message_id + 1})
                    nextmsg = sendMessage(message_args[0], bot, nextmsg)
                    nextmsg.from_user.id = message.from_user.id
                    multi -= 1
                    sleep(3)
                    Thread(target=_mirror, args=(bot, nextmsg, isZip, extract, isQbit, isLeech, pswd, multi)).start()
                return
            else:
                link = file.get_file().file_path

    if len(mesg) > 1:
        try:
            ussr = quote(mesg[1], safe='')
            pssw = quote(mesg[2], safe='')
            link = link.split("://", maxsplit=1)
            link = f'{link[0]}://{ussr}:{pssw}@{link[1]}'
        except:
            pass

    if not is_url(link) and not is_magnet(link) and not ospath.exists(link):
        help_msg = "Send link along with command line"
        help_msg += "\nor reply to link or file"
        msg = sendMessage(help_msg, bot, update)
        Thread(target=auto_delete_message, args=(bot, update.message, msg)).start()

    LOGGER.info(link)

    if not is_mega_link(link) and not isQbit and not is_magnet(link) \
        and not is_gdrive_link(link) and not link.endswith('.torrent'):
        content_type = get_content_type(link)
        if content_type is None or match(r'text/html|text/plain', content_type):
            try:
                is_gdtot = is_gdtot_link(link)
                link = direct_link_generator(link)
                LOGGER.info(f"Generated link: {link}")
            except DirectDownloadLinkException as e:
                LOGGER.info(str(e))
                if str(e).startswith('ERROR:'):
                    return sendMessage(str(e), bot, update)
    elif isQbit and not is_magnet(link) and not ospath.exists(link):
        if link.endswith('.torrent'):
            content_type = None
        else:
            content_type = get_content_type(link)
        if content_type is None or match(r'application/x-bittorrent|application/octet-stream', content_type):
            try:
                resp = requests.get(link, timeout=10, headers = {'user-agent': 'Wget/1.12'})
                if resp.status_code == 200:
                    file_name = str(time()).replace(".", "") + ".torrent"
                    with open(file_name, "wb") as t:
                        t.write(resp.content)
                    link = str(file_name)
                else:
                    return sendMessage(f"{tag} ERROR: link got HTTP response: {resp.status_code}", bot, message)
            except Exception as e:
                error = str(e).replace('<', ' ').replace('>', ' ')
                if error.startswith('No connection adapters were found for'):
                    link = error.split("'")[1]
                else:
                    LOGGER.error(str(e))
                    return sendMessage(tag + " " + error, bot, update)
        else:
            msg = "Qb commands for torrents only. if you are trying to dowload torrent then report."
            return sendMessage(msg, bot, update)

    listener = MirrorListener(bot, update, isZip, extract, isQbit, isLeech, pswd, tag)

    if is_gdrive_link(link):
        if not isZip and not extract and not isLeech:
            gmsg = f"Use /{BotCommands.CloneCommand} to clone Google Drive file/folder\n\n"
            gmsg += f"Use /{BotCommands.ZipMirrorCommand} to make zip of Google Drive folder\n\n"
            gmsg += f"Use /{BotCommands.UnzipMirrorCommand} to extracts Google Drive archive file"
            return sendMessage(gmsg, bot, update)
        Thread(target=add_gd_download, args=(link, listener, is_gdtot)).start()

    elif is_mega_link(link):
        if BLOCK_MEGA_LINKS:
            return sendMessage("Mega links are blocked!", bot, update)
        link_type = get_mega_link_type(link)
        if link_type == "folder" and BLOCK_MEGA_FOLDER:
            sendMessage("Mega folder are blocked!", bot, update)
        else:
            if MEGAREST:
                mega_dl = MegaDownloadeHelper(listener).add_rest_download
            else:
                mega_dl = add_mega_download
            Thread(target=mega_dl, args=(link, f'{DOWNLOAD_DIR}{listener.uid}/', listener)).start()
            '''
            if link_type == "folder":
                sendMessage(f"{uname}, <b>Your Requested MEGA Folder Has Been Added To</b> /{BotCommands.StatusCommand}", bot, update)
            else:
                sendMessage(f"{uname}, <b>Your Requested MEGA File Has Been Added To</b> /{BotCommands.StatusCommand}", bot, update)
                '''

    elif isQbit and (is_magnet(link) or ospath.exists(link)):
        Thread(target=add_qb_torrent, args=(link, f'{DOWNLOAD_DIR}{listener.uid}', listener, qbitsel)).start()

    else:
        Thread(target=add_aria2c_download, args=(link, f'{DOWNLOAD_DIR}{listener.uid}', listener, name)).start()

    if multi > 1:
        sleep(3)
        nextmsg = type('nextmsg', (object, ), {'chat_id': message.chat_id, 'message_id': message.reply_to_message.message_id + 1})
        nextmsg = sendMessage(message_args[0], bot, nextmsg)
        nextmsg.from_user.id = message.from_user.id
        multi -= 1
        sleep(3)
        Thread(target=_mirror, args=(bot, nextmsg, isZip, extract, isQbit, isLeech, pswd, multi)).start()


def mirror(update, context):
    _mirror(context.bot, update)

def unzip_mirror(update, context):
    _mirror(context.bot, update, extract=True)

def zip_mirror(update, context):
    _mirror(context.bot, update, True)

def qb_mirror(update, context):
    _mirror(context.bot, update, isQbit=True)

def qb_unzip_mirror(update, context):
    _mirror(context.bot, update, extract=True, isQbit=True)

def qb_zip_mirror(update, context):
    _mirror(context.bot, update, True, isQbit=True)

def leech(update, context):
    _mirror(context.bot, update, isLeech=True)

def unzip_leech(update, context):
    _mirror(context.bot, update, extract=True, isLeech=True)

def zip_leech(update, context):
    _mirror(context.bot, update, True, isLeech=True)

def qb_leech(update, context):
    _mirror(context.bot, update, isQbit=True, isLeech=True)

def qb_unzip_leech(update, context):
    _mirror(context.bot, update, extract=True, isQbit=True, isLeech=True)

def qb_zip_leech(update, context):
    _mirror(context.bot, update, True, isQbit=True, isLeech=True)

mirror_handler = CommandHandler(BotCommands.MirrorCommand, mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
unzip_mirror_handler = CommandHandler(BotCommands.UnzipMirrorCommand, unzip_mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
zip_mirror_handler = CommandHandler(BotCommands.ZipMirrorCommand, zip_mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
qb_mirror_handler = CommandHandler(BotCommands.QbMirrorCommand, qb_mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
qb_unzip_mirror_handler = CommandHandler(BotCommands.QbUnzipMirrorCommand, qb_unzip_mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
qb_zip_mirror_handler = CommandHandler(BotCommands.QbZipMirrorCommand, qb_zip_mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
if LEECH_ENABLED:
    leech_handler = CommandHandler(BotCommands.LeechCommand, leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
    unzip_leech_handler = CommandHandler(BotCommands.UnzipLeechCommand, unzip_leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
    zip_leech_handler = CommandHandler(BotCommands.ZipLeechCommand, zip_leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
    qb_leech_handler = CommandHandler(BotCommands.QbLeechCommand, qb_leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
    qb_unzip_leech_handler = CommandHandler(BotCommands.QbUnzipLeechCommand, qb_unzip_leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
    qb_zip_leech_handler = CommandHandler(BotCommands.QbZipLeechCommand, qb_zip_leech,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
else:
    leech_handler = CommandHandler(BotCommands.LeechCommand, leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
    unzip_leech_handler = CommandHandler(BotCommands.UnzipLeechCommand, unzip_leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
    zip_leech_handler = CommandHandler(BotCommands.ZipLeechCommand, zip_leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
    qb_leech_handler = CommandHandler(BotCommands.QbLeechCommand, qb_leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
    qb_unzip_leech_handler = CommandHandler(BotCommands.QbUnzipLeechCommand, qb_unzip_leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
    qb_zip_leech_handler = CommandHandler(BotCommands.QbZipLeechCommand, qb_zip_leech,
                                filters=CustomFilters.owner_filter | CustomFilters.authorized_user, run_async=True)
dispatcher.add_handler(mirror_handler)
dispatcher.add_handler(unzip_mirror_handler)
dispatcher.add_handler(zip_mirror_handler)
dispatcher.add_handler(qb_mirror_handler)
dispatcher.add_handler(qb_unzip_mirror_handler)
dispatcher.add_handler(qb_zip_mirror_handler)
dispatcher.add_handler(leech_handler)
dispatcher.add_handler(unzip_leech_handler)
dispatcher.add_handler(zip_leech_handler)
dispatcher.add_handler(qb_leech_handler)
dispatcher.add_handler(qb_unzip_leech_handler)
dispatcher.add_handler(qb_zip_leech_handler)

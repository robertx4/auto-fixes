import asyncio
import shlex

from bot.database import MongoDB
from pyrogram import enums


async def get_user_quality(user_id: int) -> str:
    try:
        user_data = MongoDB().find_one(user_id)
        return user_data["yt_qual"]
    except Exception as ex:
        return "720p"


async def fetch_format_info(url: str) -> list:
    args = ["yt-dlp", "--list-formats", url]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    format_info = stdout.decode().splitlines()
    return format_info


async def get_best_format(user_quality: str, format_info: list) -> str:
    for line in format_info:
        if ("av01" in line or "vp09" in line) and user_quality in line:
            return line.split()[0]

    if all(user_quality not in line for line in format_info):
        for line in format_info:
            if "av01" in line:
                return "bv[vcodec^=av01]"

        for line in format_info:
            if "vp09" in line:
                return "bv[vcodec^=vp09]"

    return "bv[vcodec^=vp09]"


async def get_audio_id(user_quality: str, format_info: list, video_format: str) -> str:
    spanish_audio_found = False
    for line in format_info:
        if "opus" in line and "[es" in line:
            audio_id = "ba[language^=es]"
            spanish_audio_found = True
            break

    if not spanish_audio_found:
        audio_id = "bestaudio"

    audio_map = {
        "360p": "wa[acodec=opus]",
        "480p": "249",
        "720p": "250",
        "1080p": "251",
    }
    for line in format_info:
        if ("av01" in line or "vp09" in line) and user_quality in line:
            audio_id = audio_map.get(user_quality, audio_id)
            break

    for tag in ("[es", "-"):
        for line in format_info:
            if audio_id in line and tag in line:
                return line.split()[0]

    return audio_id


async def generate_dl_command(
    url: str,
    user_id: int,
    username: str,
    user_quality: str,
    format_info: list,
    video_format: str,
    audio_format: str,
) -> str:
    command1 = f"yt-dlp --no-warnings -f {video_format}+{audio_format}"

    for line in format_info:
        if (audio_format in line and "[es" not in line) or audio_format == "bestaudio":
            command1 += " --write-auto-subs"
            break

    command1 += (
        " --sub-langs es.* --embed-subs --embed-thumbnail --embed-metadata"
        " --parse-metadata description:(?s)(?P<meta_comment>.+) --convert-subs ass"
        f" --convert-thumbnails jpg -o Root/{username}/%(title)s.%(ext)s {url}"
    )

    command2 = (
        "yt-dlp --write-thumbnail --no-warnings --skip-download --convert-thumbnails"
        f" jpg -o Root/thumbs/{user_id}/%(title)s.%(ext)s {url}"
    )

    return [command1, command2]


async def exec_command(commands: list, message, dl_message):
    for command in commands:
        args = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            await dl_message.edit_text(
                f"```{stderr.decode()}```", parse_mode=enums.ParseMode.MARKDOWN
            )
            return

        await proc.wait()

    await dl_message.edit_text(
        "✅ <b>Video Downloaded Successfully\nUse <i>/ls</i> To View Directory</b>"
    )


async def Youtube_CLI(message, url: str):
    user_id = message.from_user.id
    username = message.from_user.username
    user_quality = await get_user_quality(user_id)

    retries = 3
    dl_message = await message.reply_text(
        "🔎 <b><i>Fetching Video Details...</i></b>", quote=True
    )

    for attempt in range(retries + 1):
        try:
            if "playlist" in url:
                await dl_message.edit_text("🚫 <b>Playlists Are Not Supported Yet.</b>")
                return

            format_info = await fetch_format_info(url)

            if all("[info] Available formats for " not in line for line in format_info):
                await dl_message.edit_text("❌ <b>Invalid YouTube URL.</b>")
                return

            video_format = await get_best_format(user_quality, format_info)
            audio_format = await get_audio_id(user_quality, format_info, video_format)

            await dl_message.edit_text(f"⬇️ <b>Downloading In {user_quality}...</b>")

            if video_format in ["bv[vcodec^=av01]", "bv[vcodec^=vp09]"]:
                await dl_message.edit_text("⚠️ <b>Selected Quality Not Available.</b>")
                await asyncio.sleep(3)
                await dl_message.edit_text("⬇️ <b>Trying Best Available...</b>")

            final_command = await generate_dl_command(
                url,
                user_id,
                username,
                user_quality,
                format_info,
                video_format,
                audio_format,
            )
            await exec_command(final_command, message, dl_message)

            break

        except Exception as ex:
            if attempt < retries:
                await dl_message.edit_text(
                    f"🔄 <b>Retrying Download ({attempt+1}/{retries})...</b>"
                )
                await asyncio.sleep(3)
            else:
                await dl_message.edit_text(
                    f"<code>{ex}</code>", parse_mode=enums.ParseMode.HTML
                )

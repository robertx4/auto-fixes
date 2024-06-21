import asyncio

from bot.database import MongoDB
from pyrogram import enums
from pyrogram.types import Message


async def get_user_quality(user_id: int) -> str:
    user_data = MongoDB().find_one(user_id)
    return user_data["yt_qual"]


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
    best_format = None

    for line in format_info:
        if ("av01" in line or "vp9" in line) and user_quality in line:
            best_format = line.split()[0]
            break

    if not best_format:
        for line in format_info:
            if "av01" in line:
                best_format = "bv[vcodec^=av01]"
                break

        if not best_format:
            for line in format_info:
                if "vp9" in line:
                    best_format = "bv[vcodec=vp9]"
                    break

    if not best_format:
        best_format = "605"

    return best_format


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
        "144p": "wa[acodec=opus]",
        "240p": "wa[acodec=opus]",
        "360p": "wa[acodec=opus]",
        "480p": "249",
        "720p": "250",
        "1080p": "251",
    }
    for line in format_info:
        if ("av01" in line or "vp9" in line) and user_quality in line:
            audio_id = audio_map.get(user_quality, audio_id)
            break

    for line in format_info:
        for tag in ("[es", "-"):
            if audio_id in line and tag in line:
                return line.split()[0]

    return audio_id


async def generate_dl_command(
    url: str,
    user_id: int,
    username: str,
    format_info: list,
    video_format: str,
    audio_format: str,
) -> list:

    command = ["yt-dlp", "--no-warnings", f"-f {video_format}+{audio_format}"]

    if (
        any(audio_format in line and "[es" not in line for line in format_info)
        or audio_format == "bestaudio"
    ):
        command.append("--write-auto-subs")

    command.extend(
        [
            "--sub-langs",
            "es.*",
            "--embed-subs",
            "--embed-thumbnail",
            "--embed-metadata",
            "--parse-metadata",
            "description:(?s)(?P<meta_comment>.+)",
            "--convert-subs",
            "ass",
            "--convert-thumbnails",
            "jpg",
            "-o",
            f"Root/{username}/%(title)s.%(ext)s",
            url,
        ]
    )

    thumbnail_command = [
        "yt-dlp",
        "--write-thumbnail",
        "--no-warnings",
        "--skip-download",
        "--convert-thumbnails",
        "jpg",
        "-o",
        f"Root/thumbs/{user_id}/%(title)s.%(ext)s",
        url,
    ]

    return [command, thumbnail_command]


async def exec_command(commands: list, message, dl_message):
    for command in commands:
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            await dl_message.edit_text(
                f"```{stderr.decode()}```", parse_mode=enums.ParseMode.MARKDOWN
            )
            return

    await dl_message.edit_text(
        "✅ <b>Video Downloaded Successfully\nUse <i>/ls</i> To View Directory</b>"
    )


async def Youtube_CLI(message: Message):
    url = message.text
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

            if video_format in ["bv[vcodec^=av01]", "bv[vcodec=vp9]"]:
                await dl_message.edit_text("⚠️ <b>Selected Quality Not Available.</b>")
                await asyncio.sleep(3)
                await dl_message.edit_text("⬇️ <b>Trying Best Available...</b>")

            elif video_format == "605":
                await dl_message.edit_text("⚠️ <b>Selected Quality Not Available.</b>")
                await asyncio.sleep(3)
                await dl_message.edit_text("⬇️ <b>Downloading In 360p...</b>")

            final_command = await generate_dl_command(
                url,
                user_id,
                username,
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

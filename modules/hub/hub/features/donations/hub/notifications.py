import discord
from datetime import datetime
from dateutil import tz

from flask import current_app
from flaskbb.user.models import User
from flaskbb.utils.helpers import discord_task
from flaskbb.extensions import discordClient
from flaskbb.utils.settings import flaskbb_config

from hub.features.donations.utils import get_donations_host_user, get_player_points_sum
from hub.models import PointsTransaction, MoneyTransaction

@discord_task
async def notify_user_donation_registration_error(dt: datetime, amount, comment: str):
    host = await get_donations_host_user()

    if not comment:
        comment = "<Отсутствует>"

    color = 0xff0000
    embed = discord.Embed(color=color)
    embed.title = "Неполучилось автоматически обработать донат!"
    embed.add_field(name="Время", value=dt.strftime("%d.%m.%y %H:%M"), inline=False)
    embed.add_field(name="Рублей задоначено", value=amount, inline=False)
    embed.add_field(name="Комментарий", value=comment, inline=False)

    if host:
        await host.send(embed=embed)


@discord_task
async def notify_user_about_points_transaction(initiator: User, transaction: PointsTransaction):
    if initiator:
        initiator: discord.User = await discordClient.fetch_user(int(initiator.discord))
    else:
        initiator = await get_donations_host_user()

    color = 0xff0000 if transaction.change < 0 else 0xffd000
    embed = discord.Embed(color=color)

    embed.add_field(name="Аккаунт BYOND", value=transaction.player.ckey, inline=False)
    embed.add_field(
        name="Потрачено опиксов" if transaction.change < 0 else "Добавлено опиксов",
        value="{:+.0f}".format(transaction.change),
        inline=False)
    embed.add_field(name="Комментарий", value=transaction.comment, inline=False)
    embed.add_field(name="Время транзакции", value=transaction.datetime.astimezone(tz.tzlocal()).strftime("%d.%m.%y %H:%M"), inline=False)

    user: discord.User = None
    if transaction.player.discord_user_id:
        user = await discordClient.fetch_user(int(transaction.player.discord_user_id))

    embed.title = "{}#{}".format(user.name, user.discriminator) if user else "Неизвестный пользователь" + \
                  (" потратил опиксы." if transaction.change < 0 else " получил опиксы.")
    if initiator:
        await initiator.send(embed=embed)

    if not user:
        return

    embed.title = "Вы потратили опиксы!" if transaction.change < 0 else "Вы получили опиксы!"
    try:
        await user.send(embed=embed)
    except discord.errors.Forbidden:
        await initiator.send("**Ошибка:** Discord запретил отправку сообщения {ckey} ({discord})"
                             .format(ckey=transaction.player.ckey, discord=transaction.player.discord_user_id))
        raise
    except Exception:
        await initiator.send("**Ошибка:** Произошла неизвестная ошибка при отправке сообщения {ckey} ({discord})"
                             .format(ckey=transaction.player.ckey, discord=transaction.player.discord_user_id))
        raise


@discord_task
async def report_money_transaction(balance, transaction: MoneyTransaction):
    reports_channel = discordClient.get_channel(current_app.config["DONATIONS_REPORT_CHANNEL_ID"])
    timestr = transaction.datetime.astimezone(tz.tzlocal()).strftime("%d.%m.%Y %H:%M")

    if transaction.change > 0:
        await reports_channel.send(
            "__{}__ _получили **{:+.0f} ₽**. Сумма: {:.0f} ₽._".format(timestr, transaction.change, balance))
    else:
        await reports_channel.send(
            "__{}__ _{}: **{:+.0f} ₽**. Сумма: {:.0f} ₽._".format(timestr, transaction.reason, transaction.change, balance))


@discord_task
async def report_points_transaction(transaction: PointsTransaction):
    reports_channel = discordClient.get_channel(current_app.config["DONATIONS_POINTS_REPORT_CHANNEL_ID"])
    timestr = transaction.datetime.astimezone(tz.tzlocal()).strftime("%d.%m.%Y %H:%M")

    message = None
    if transaction.change > 0:
        message = "\n_**{}** добавили **{:+.0f}** опиксов: \"{}\"_".format(
                transaction.player.ckey,
                transaction.change,
                transaction.comment)
    else:
        message = "\n_**{}** сняли **{:+.0f}** опиксов: \"{}\"_".format(
                transaction.player.ckey,
                transaction.change,
                transaction.comment)

    summary = get_player_points_sum(transaction.player)
    message += "\n_Текущий баланс: {:.0f} опиксов._".format(summary)
    await reports_channel.send(message)

# bot.py
import re
from aiocqhttp import CQHttp, Event
from xiaoai import set_authorization, get_models_list, delete, \
    start, get_ptts_list, verify, MsgException, share, audition, invite_record, \
    models_ranking

bot = CQHttp()


@bot.on_message('private')
async def _(event: Event):
    msg = await set_authorization(event.user_id, event.message.strip())
    await bot.send(event, msg)


@bot.on_message('group')
async def _(event: Event):
    msg = event.message.strip()
    qq = event.user_id
    if msg == "模型列表":
        result = get_models_list()
        await bot.send(event, result, at_sender=True)
        return
    if msg == "音色列表" or msg == "我的音色" or msg == "删除音色":
        result = await get_ptts_list(qq)
        await bot.send(event, result, at_sender=True)

    if msg == "帮录" or msg == "生成帮录链接" or msg == "帮录链接":
        result = await invite_record(qq)
        await bot.send(event, result, at_sender=True)

    if msg == "模型排行":
        result = models_ranking()
        await bot.send(event, result, at_sender=True)

    r = re.search(r"^删除(音色)?\s*(.+)$", msg)
    if r:
        name = r.group(2).strip()
        result = await delete(qq, name)
        await bot.send(event, result, at_sender=True)
        return
    r = re.search(r"^分享(音色)?\s*(.+)$", msg)
    if r:
        name = r.group(2).strip()
        result = await share(qq, name)
        await bot.send(event, result, at_sender=True)
        return
    r = re.search(r"^训练\s*(.+)$", msg)
    if r:
        name = r.group(1)
        try:
            headers, name = await verify(qq, name)
        except MsgException as e:
            await bot.send(event, str(e.message), at_sender=True)
            return
        result = await start(headers, name, qq, event.sender['nickname'])
        await bot.send(event, result, at_sender=True)
        return
    r = re.search(r"^试听(音色)?\s*(.+)$", msg)
    if r:
        name = r.group(2).strip()
        result = audition(name)
        await bot.send(event, result, at_sender=True)
        return


bot.run(host='127.0.0.1', port=8080)

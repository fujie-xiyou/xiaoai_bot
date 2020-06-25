import json
import os
from typing import List, Set

import aiohttp
import redis
import random
import string
import logging
import ssl

from config import *

logging.basicConfig(level=logging.INFO, filename="xiaoai.log")

ssl._create_default_https_context = ssl._create_unverified_context

models_path = os.path.join(os.path.expanduser("~"), "Desktop", "models")
redis_pool = redis.ConnectionPool(host='localhost', max_connections=20)


def group_message_async(func):
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
        except MsgException as e:
            result = e.message
        return result

    return wrapper


def group_message(func):
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except MsgException as e:
            result = e.message
        return result

    return wrapper


class MsgException(Exception):
    def __init__(self, message, raw_exception=None):
        super().__init__(message)
        self.message = message
        self.raw_exception = raw_exception


async def _get_headers_and_models_by_auth(auth: str):
    headers = {
        "user-agent": "Mi 10; MIAI/5.8.6-202004101658-28 Build/305008006 Channel/MIUI20.3.28 Device/umi OS/10 SDK/29 "
                      "Flavors/upgrade28",
        "Authorization": auth
    }
    async with aiohttp.ClientSession() as session:
        async with session.get("https://speech.ai.xiaomi.com/speech/v1.0/ptts/list",
                               headers=headers,
                               timeout=5000) as resp:
            if resp.status == 200:
                resp_json = await resp.json(content_type=None)
                if resp_json["code"] != 200:
                    raise MsgException("授权码已经失效，请重新私聊我发送")
            else:
                raise MsgException("授权码已经失效，请重新私聊我发送")
            models = resp_json["models"].get("Owner", [])
            return headers, models


async def _get_headers_and_models_by_qq(qq):
    r = redis.Redis(connection_pool=redis_pool)
    auth = r.hget("xiaoai:auth", key=qq)
    r.close()
    if not auth:
        raise MsgException("请先私聊我发送小爱同学授权码(抓包获取)")
    return await _get_headers_and_models_by_auth(auth.decode())


@group_message_async
async def delete(qq, name):
    headers, models = await _get_headers_and_models_by_qq(qq)
    delete_model = None
    for model in models:
        if model["name"].lower() == name.lower():
            delete_model = model
            break
    if not delete_model:
        raise MsgException(f"你没有名为 {name} 的音色。")
    delete_data = {"model_name": delete_model["name"],
                   "device_id": ''.join(random.sample(string.ascii_letters + string.digits, 22)),
                   "vendor_id": delete_model["vendor_id"],
                   "request_id": "ptts_{}".format(''.join(random.sample(string.ascii_letters + string.digits, 22)))}
    async with aiohttp.ClientSession() as session:
        async with session.delete("https://speech.ai.xiaomi.com/speech/v1.0/ptts/model",
                                  headers=headers,
                                  json=delete_data,
                                  timeout=5000) as resp:
            if resp.status == 200:
                resp_json = await resp.json(content_type=None)
                if resp_json["code"] == 200:
                    return f"音色 {delete_model['name']} 删除成功。"
                else:
                    return resp_json['message']
            else:
                return f"删除失败，错误码：{resp.status}"


@group_message_async
async def share(qq, name):
    headers, models = await _get_headers_and_models_by_qq(qq)
    share_model = None
    lower_name = name.lower()
    for model in models:
        if model["name"].lower() == lower_name:
            share_model = model
            break
    if not share_model:
        raise MsgException(f"你没有名为 {name} 的音色。")
    delete_data = {
        "device_id": ''.join(random.sample(string.ascii_letters + string.digits, 22)),
        "vendor_id": share_model["vendor_id"],
        "request_id": "ptts_{}".format(''.join(random.sample(string.ascii_letters + string.digits, 22)))}
    async with aiohttp.ClientSession() as session:
        async with session.post("https://speech.ai.xiaomi.com/speech/v1.0/ptts/share_link",
                                headers=headers,
                                json=delete_data,
                                timeout=5000) as resp:
            if resp.status == 200:
                resp_json = await resp.json(content_type=None)
                if resp_json["code"] == 200:
                    share_link = resp_json['share_link']
                    # 短网址动不动就被封气死人
                    # url_data = {
                    #     "username": YOURLS_USERNAME,
                    #     "password": YOURLS_PASSWORD,
                    #     "action": "shorturl",
                    #     "format": "json",
                    #     "url": share_link
                    # }
                    # async with session.post("http://u.fujie.bid:81/yourls-api.php",
                    #                         data=url_data) as url_resp:
                    #     if url_resp.status == 200 and (await url_resp.json(content_type=None))["statusCode"] == 200:
                    #         url_resp_json = await url_resp.json(content_type=None)
                    #         share_link = url_resp_json["shorturl"]
                    r = redis.Redis(connection_pool=redis_pool)
                    r.hset(name="xiaoai:model:link", key=name, value=share_link)
                    r.close()
                    return f"分享的音色 {share_model['name']} 链接如下：\n{share_link}"
                else:
                    return resp_json['message']
            else:
                return f"分享失败，错误码：{resp.status}"


@group_message
def audition(name):
    r = redis.Redis(connection_pool=redis_pool)
    share_link: bytes = r.hget(name="xiaoai:model:link", key=name)
    r.close()
    if share_link:
        share_link: str = share_link.decode()
        return f"试听音色 {name}，链接如下：\n{share_link}"
    else:
        return f"还没有人分享过这个音色。"


async def set_authorization(qq, auth: str):
    try:
        await _get_headers_and_models_by_auth(auth)
    except MsgException:
        return "授权码无效，请重新发送。"
    r = redis.Redis(connection_pool=redis_pool)
    try:
        r.hset("xiaoai:auth", key=qq, value=auth)
        return f"设置成功，请在群聊中使用训练功能。"
    except Exception as e:
        logging.exception(e)
        return "写入失败。请重试"
    finally:
        r.close()


def _get_models_list(lower=False):
    models = [m.split(".")[0] for m in os.listdir(models_path) if m.endswith(".json")]
    return [m.lower() if lower else m for m in models]


@group_message
def get_models_list():
    models_dirs = _get_models_list()
    models_dirs = sorted(models_dirs, key=lambda x: os.path.getmtime(os.path.join(models_path, f"{x}.json")),
                         reverse=True)
    r = redis.Redis(connection_pool=redis_pool)
    shared_models: List[bytes] = r.hkeys(name="xiaoai:model:link")
    r.close()
    shared_models: Set[str] = {m.decode('utf-8') for m in shared_models}
    models_dirs = [f"{m}*" if m in shared_models else m for m in models_dirs]
    result = "当前支持训练的模型有(标有*的模型支持试听)：\n"
    result += "，".join(models_dirs)
    logging.debug(result)
    return result


def _show_ptts_list(models):
    status = {
        "Waiting": "等待训练..",
        "Training": "训练中..",
        "Done": "完成",
        "Audit": "审核中.."
    }
    i = 1
    res_str = ""
    for model in models:
        status_str = model['status']
        res_str += f"{i}. 音色名：{model['name']} 状态：{status.get(status_str, status_str)}"
        if status_str == "Training" or status_str == "Waiting":
            res_str += f" 剩余时间：{model['remaining'] // 60} 分钟\n"
        else:
            res_str += "\n"
        i += 1
    return res_str


@group_message_async
async def get_ptts_list(qq):
    headers, models = await _get_headers_and_models_by_qq(qq)
    res_str = "你的音色列表如下：\n"
    res_str += _show_ptts_list(models)
    res_str += "如需删除，请输入 删除音色+音色名，例如：删除音色卢姥爷"
    return res_str


async def verify(qq, name):
    headers, models = await _get_headers_and_models_by_qq(qq)
    if len(models) >= 5:
        res_str = "你的音色列表已经满了，请发送 删除音色+音色名 (例如：删除音色卢姥爷) 删除音色后再操作\n"
        res_str += "音色列表如下：\n"
        res_str += _show_ptts_list(models)
        raise MsgException(res_str)
    models = _get_models_list()
    name_lower = name.lower()
    has_model = False
    for m in models:
        if name_lower == m.lower():
            name = m
            has_model = True
            break
    if not has_model:
        raise MsgException("没有这个模型，发送模型列表查看支持训练的模型。")
    return headers, name


async def _post_record(headers, post_data, name):
    post_data["model_name"] = name
    async with aiohttp.ClientSession() as session:
        async with session.post("https://speech.ai.xiaomi.com/speech/v1.0/ptts/train",
                                json=post_data,
                                headers=headers,
                                timeout=5) as resp:
            if resp.status == 200:
                resp_json = await resp.json(content_type=None)
                if int(resp_json["code"]) == 200:
                    r = redis.Redis(connection_pool=redis_pool)
                    r.hincrby("xiaoai:model", key=name)
                    r.close()
                    return "提交成功，发送“音色列表”或者进入小爱音色列表查看状态。"
                else:
                    raise MsgException("提交失败，{} 错误码: {}".format(resp_json["details"], resp_json["code"]))
            else:
                raise MsgException("提交训练失败，code: %s, resp: %s" % (resp.status, await resp.text()))


@group_message_async
async def invite_record(qq):
    headers, models = await _get_headers_and_models_by_qq(qq)
    request_id = "ptts_{}".format(''.join(random.sample(string.ascii_letters + string.digits, 22)))
    device_id = ''.join(random.sample(string.ascii_letters + string.digits, 22))
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://speech.ai.xiaomi.com/speech/v1.0/ptts/token"
                               f"?request_id={request_id}&device_id={device_id}",
                               headers=headers,
                               timeout=5) as resp:
            if resp.status == 200:
                resp_json = await resp.json(content_type=None)
                if resp_json['code'] == 200:
                    invite_code = resp_json['token']
                    invite_url = f"https://i.ai.mi.com/h5/ai-custom-tts-fe/index.html?inviteCode={invite_code}"
                    return f"你的邀请录制链接如下：\n{invite_url}"
                else:
                    raise MsgException(f'操作失败，原因：{resp_json["details"]} 错误码:{resp_json["code"]}')
            else:
                return f"操作失败，http状态码：{resp.status}，resp: {resp.text()}"


@group_message
def models_ranking():
    r = redis.Redis(connection_pool=redis_pool)
    models_count = r.hgetall(name="xiaoai:model").items()
    r.close()
    models_count = sorted(models_count, key=lambda o: int(o[1]), reverse=True)
    result = "模型被训练次数排行如下：\n"
    for mc in models_count:
        result += f"{mc[0].decode('utf-8')}({int(mc[1])}次)，"
    return result[:-1]


@group_message_async
async def start(headers, name):
    json_path = os.path.join(models_path, f"{name}.json")
    f = open(json_path, "r", encoding="gb18030")
    try:
        json_str = f.read()
    except UnicodeDecodeError:
        f.close()
        f = open(json_path, "r", encoding="utf-8")
        json_str = f.read()

    f.close()
    post_data = json.loads(json_str)
    return await _post_record(headers, post_data, name)

import os
import requests
import ahttp
import redis
import random
import string
import logging
logging.basicConfig(level=logging.DEBUG)

models_path = "C:\\Users\\10148\\Desktop\\models"
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


def _get_headers_and_models_by_auth(auth):
    headers = {
        "user-agent": "Mi 10; MIAI/5.8.6-202004101658-28 Build/305008006 Channel/MIUI20.3.28 Device/umi OS/10 SDK/29 "
                      "Flavors/upgrade28",
        "Authorization": auth
    }
    times = 3
    while True:
        times -= 1
        try:
            resp = requests.get("https://speech.ai.xiaomi.com/speech/v1.0/ptts/list",
                                headers=headers,
                                timeout=5)
            break
        except requests.exceptions.RequestException:
            if times > 0:
                logging.warning("请求超时，正在重试...")
                continue
            else:
                raise MsgException("请求失败，请稍候再试。")
        except Exception as e:
            logging.info(str(e))
            raise MsgException("授权码无效。")
    if resp.status_code == 200:
        resp_json = resp.json()
        if resp_json["code"] != 200:
            raise MsgException("授权码已经失效，请重新私聊我发送")
    else:
        raise MsgException("授权码已经失效，请重新私聊我发送")
    models = resp_json["models"]["Owner"]
    return headers, models


def _get_headers_and_models_by_qq(qq):
    r = redis.Redis(connection_pool=redis_pool)
    auth = r.get(f"auth:{qq}")
    r.close()
    if not auth:
        raise MsgException("请先私聊我发送小爱同学授权码(抓包获取)")
    return _get_headers_and_models_by_auth(auth)


@group_message_async
async def delete(qq, name):
    headers, models = _get_headers_and_models_by_qq(qq)
    delete_model = None
    for model in models:
        if model["name"] == name:
            delete_model = model
            break
    if not delete_model:
        raise MsgException(f"你没有名为 {name} 的音色。")
    delete_data = {"model_name": delete_model["name"],
                   "device_id": ''.join(random.sample(string.ascii_letters + string.digits, 22)),
                   "vendor_id": delete_model["vendor_id"],
                   "request_id": "ptts_{}".format(''.join(random.sample(string.ascii_letters + string.digits, 22)))}

    while True:
        try:
            resp = requests.delete("https://speech.ai.xiaomi.com/speech/v1.0/ptts/model",
                                   headers=headers,
                                   json=delete_data,
                                   timeout=5)
            break
        except requests.exceptions.RequestException:
            print("请求超时，正在重试...")
            continue
    if resp.status_code == 200:
        resp_json = resp.json()
        if resp_json["code"] == 200:
            return f"音色 {delete_model['name']} 删除成功。"
        else:
            return resp_json['message']
    else:
        return f"删除失败，错误码：{resp.status_code}"


async def set_authorization(qq, auth: str):
    try:
        _get_headers_and_models_by_auth(auth)
    except MsgException:
        return "授权码无效，请重新发送。"
    r = redis.Redis(connection_pool=redis_pool)
    try:
        r.set(f"auth:{qq}", auth)
        return f"设置成功，请在群聊中使用训练功能。"
    except Exception as e:
        logging.exception(e)
        return "写入失败。请重试"
    finally:
        r.close()


@group_message_async
async def get_models_list():
    models_dirs = os.listdir(models_path)
    result = "当前支持训练的模型有："
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
    headers, models = _get_headers_and_models_by_qq(qq)
    res_str = "你的音色列表如下：\n"
    res_str += _show_ptts_list(models)
    res_str += "如需删除，请输入 删除音色+音色名，例如：删除音色卢姥爷"
    return res_str


async def verify(qq, name):
    headers, models = _get_headers_and_models_by_qq(qq)
    if len(models) >= 5:
        res_str = "你的音色列表已经满了，请发送 删除音色+音色名 (例如：删除音色卢姥爷) 删除音色后再操作\n"
        res_str += "音色列表如下：\n"
        res_str += _show_ptts_list(models)
        raise MsgException(res_str)
    models_dirs = os.listdir(models_path)
    if name not in models_dirs:
        raise MsgException("没有这个模型，发送模型列表查看支持训练的模型")
    return headers


def _upload_record(headers, name):
    upload_data = {
        "audio_data": "",
        "audio_format": {
            "codec": "pcm",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "lang": "zh-CN"
        },
        "request_id": ""
    }
    post_data = {
        "train_data_url": [
        ],
        "device_id": ''.join(random.sample(string.ascii_letters + string.digits, 22)),
        "audio_format": {
            "codec": "pcm",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "lang": "zh-CN"
        },
        "request_id": ''.join(random.sample(string.ascii_letters + string.digits, 22))
    }
    work_path = os.path.join(models_path, name)
    texts_path = os.path.join(work_path, "texts.txt")
    try:
        text = open(texts_path, encoding="gb18030")
        try:
            texts = text.readlines()
        except UnicodeDecodeError:
            text.close()
            text = open(texts_path, encoding="utf-8")
            texts = text.readlines()
        text.close()
        texts = [text.strip() for text in texts if text.strip()]

    except FileNotFoundError:
        raise MsgException("模型异常，未找到 texts.txt")
    n = len(texts) + 1
    for i in range(1, n):
        with open(os.path.join(work_path, "%s.b64" % i), "r") as f:
            audio_data = f.read()
            upload_data["audio_data"] = audio_data
            upload_data["request_id"] = ''.join(random.sample(string.ascii_letters + string.digits, 22))
            while True:
                try:
                    resp = requests.post("https://speech.ai.xiaomi.com/speech/v1.0/ptts/upload",
                                         json=upload_data,
                                         headers=headers,
                                         timeout=5)
                    if resp.status_code == 200:
                        resp_json = resp.json()
                        if resp_json["code"] == 200:
                            item = {"url": resp_json["audio_file"], "id": str(i), "text": texts[i - 1]}
                            post_data["train_data_url"].append(item)
                            break
                        else:
                            continue
                    else:
                        continue
                except requests.exceptions.RequestException:
                    continue
    gender_path = os.path.join(work_path, "gender.txt")
    try:
        gender_f = open(gender_path, encoding="gb18030")
        try:
            gender = gender_f.readline()
        except UnicodeDecodeError:
            gender_f.close()
            gender_f = open(gender_path, encoding="utf-8")
            gender = gender_f.readline()
        gender_f.close()
        post_data["user_gender"] = gender.strip()
        post_data["model_name"] = name
    except FileNotFoundError:
        raise MsgException("模型异常。未找到 gender.txt")

    return post_data


def _post_record(headers, post_data):
    while True:
        try:
            resp = requests.post("https://speech.ai.xiaomi.com/speech/v1.0/ptts/train",
                                 json=post_data,
                                 headers=headers,
                                 timeout=5)
            break
        except requests.exceptions.RequestException:
            logging.warning("请求超时，正在重试...")
            continue
    if resp.status_code == 200:
        resp_json = resp.json()
        if int(resp_json["code"]) == 200:
            return "提交成功，请进入小爱音色列表查看"
        else:
            raise MsgException("提交失败，{} 错误码: {}".format(resp_json["details"], resp_json["code"]))
    else:
        raise MsgException("提交训练失败，code: %s, resp: %s" % (resp.status_code, resp.text))


@group_message_async
async def start(headers, name):
    post_data = _upload_record(headers, name)
    return _post_record(headers, post_data)

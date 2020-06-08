from nonebot import on_command, CommandSession
from xiaoai.xiaoai import delete


# on_command 装饰器将函数声明为一个命令处理器
@on_command('删除音色', only_to_me=False)
async def delete(session: CommandSession):
    # 从会话状态（session.state）中获取城市名称（city），如果当前不存在，则询问用户
    name = session.get('name')
    # 获取城市的天气预报
    # weather_report = await get_weather_of_city(city)
    # 向用户发送天气预报
    qq = session.ctx['sender']['user_id']
    msg = await delete(qq, name)
    await session.send(msg, at_sender=True)


# weather.args_parser 装饰器将函数声明为 delete 命令的参数解析器
# 命令解析器用于将用户输入的参数解析成命令真正需要的数据
@delete.args_parser
async def _(session: CommandSession):
    # 去掉消息首尾的空白符
    stripped_arg = session.current_arg_text.strip()

    if session.is_first_run:
        # 该命令第一次运行（第一次进入命令会话）
        if stripped_arg:
            # 第一次运行参数不为空，意味着用户直接将城市名跟在命令名后面，作为参数传入
            # 例如用户可能发送了：天气 南京
            session.state['name'] = stripped_arg
            return
        else:
            session.pause()

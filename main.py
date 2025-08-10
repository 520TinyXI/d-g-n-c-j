import random
import asyncio
import os
import json
import datetime
import time
import aiohttp
import urllib.parse
import logging
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
from astrbot.api.all import AstrMessageEvent, CommandResult, Context, Image, Video, Plain, MessageChain
import astrbot.api.event.filter as filter
from astrbot.api.star import register, Star

logger = logging.getLogger("astrbot")


@register("D-G-N-C-J", "Tinyxi", "", "", "")
class Main(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.PLUGIN_NAME = "astrbot_plugin_essential"
        PLUGIN_NAME = self.PLUGIN_NAME
        path = os.path.abspath(os.path.dirname(__file__))
        self.mc_html_tmpl = open(
            path + "/templates/mcs.html", "r", encoding="utf-8"
        ).read()
        self.what_to_eat_data: list = json.loads(
            open(path + "/resources/food.json", "r", encoding="utf-8").read()
        )["data"]

        if not os.path.exists(f"data/{PLUGIN_NAME}_data.json"):
            with open(f"data/{PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
                f.write(json.dumps({}, ensure_ascii=False, indent=2))
        with open(f"data/{PLUGIN_NAME}_data.json", "r", encoding="utf-8") as f:
            self.data = json.loads(f.read())
        self.good_morning_data = self.data.get("good_morning", {})

        # moe
        self.moe_urls = [
            "https://t.mwm.moe/pc/",
            "https://t.mwm.moe/mp",
            "https://www.loliapi.com/acg/",
            "https://www.loliapi.com/acg/pc/",
        ]

        self.search_anmime_demand_users = {}
        self.daily_sleep_cache = {}
        self.good_morning_cd = {} 

    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"
    
    def get_cached_sleep_count(self, umo_id: str, date_str: str) -> int:
        """获取缓存的睡觉人数"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        return self.daily_sleep_cache[umo_id].get(date_str, -1)

    def update_sleep_cache(self, umo_id: str, date_str: str, count: int):
        """更新睡觉人数缓存"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        self.daily_sleep_cache[umo_id][date_str] = count

    def invalidate_sleep_cache(self, umo_id: str, date_str: str):
            """使缓存失效"""
            if umo_id in self.daily_sleep_cache and date_str in self.daily_sleep_cache[umo_id]:
                del self.daily_sleep_cache[umo_id][date_str]

    def check_good_morning_cd(self, user_id: str, current_time: datetime.datetime) -> bool:
        """检查用户是否在CD中，返回True表示在CD中"""
        if user_id not in self.good_morning_cd:
            return False
        
        last_time = self.good_morning_cd[user_id]
        time_diff = (current_time - last_time).total_seconds()
        return time_diff < 1800  # 硬编码30分钟

    def update_good_morning_cd(self, user_id: str, current_time: datetime.datetime):
        """更新用户的CD时间"""
        self.good_morning_cd[user_id] = current_time

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_search_anime(self, message: AstrMessageEvent):
        """检查是否有搜番请求"""
        sender = message.get_sender_id()
        if sender in self.search_anmime_demand_users:
            message_obj = message.message_obj
            url = "https://api.trace.moe/search?anilistInfo&url="
            image_obj = None
            for i in message_obj.message:
                if isinstance(i, Image):
                    image_obj = i
                    break
            try:
                try:
                    # 需要经过url encode
                    image_url = urllib.parse.quote(image_obj.url)
                    url += image_url
                except BaseException as _:
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult().error(
                        f"发现不受本插件支持的图片数据：{type(image_obj)}，插件无法解析。"
                    )

                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            if sender in self.search_anmime_demand_users:
                                del self.search_anmime_demand_users[sender]
                            return CommandResult().error("请求失败")
                        data = await resp.json()

                if data["result"] and len(data["result"]) > 0:
                    # 番剧时间转换为x分x秒
                    data["result"][0]["from"] = self.time_convert(
                        data["result"][0]["from"]
                    )
                    data["result"][0]["to"] = self.time_convert(data["result"][0]["to"])

                    warn = ""
                    if float(data["result"][0]["similarity"]) < 0.8:
                        warn = "相似度过低，可能不是同一番剧。建议：相同尺寸大小的截图; 去除四周的黑边\n\n"
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult(
                        chain=[
                            Plain(
                                f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"
                            ),
                            Image.fromURL(data["result"][0]["image"]),
                        ],
                        use_t2i_=False,
                    )
                else:
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult(True, False, [Plain("没有找到番剧")], "sf")
            except Exception as e:
                raise e

    @filter.command("喜报")
    async def congrats(self, message: AstrMessageEvent):
        """喜报生成器"""
        msg = message.message_str.replace("喜报", "").strip()
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]

        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/congrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", 65)

        # Calculate the width and height of the text
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]

        # Calculate the starting position of the text to center it.
        x = (img.size[0] - text_width) / 2
        y = (img.size[1] - text_height) / 2

        draw.text(
            (x, y),
            msg,
            font=font,
            fill=(255, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 0),
        )

        img.save("congrats_result.jpg")
        return CommandResult().file_image("congrats_result.jpg")

    @filter.command("查询天气")
    async def weather_query(self, message: AstrMessageEvent):
        """天气查询功能"""
        message_str = message.message_str.replace("查询天气", "").strip()
        
        if not message_str:
            return CommandResult().error("正确指令：查询天气 地区")
        
        city = message_str
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://api.yuxli.cn/api/tianqi.php?msg={urllib.parse.quote(city)}&b=1") as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        # 解析API返回的天气信息
                        weather_data = self.parse_weather_data(result)
                        return CommandResult(chain=[Plain(weather_data)])
                    else:
                        return CommandResult().error(f"获取天气信息失败，错误码：{resp.status}")
        except Exception as e:
            return CommandResult().error(f"查询天气信息时出现错误：{str(e)}")
    
    def parse_weather_data(self, api_result):
        """解析天气API返回的数据并格式化输出"""
        # 解析API返回的数据，提取城市、日期、温度、天气、风度、空气质量信息
        # 按照用户要求的格式输出
        
        # 示例解析逻辑，根据实际API返回格式调整
        parts = api_result.split('☁.')
        formatted_output = ""
        
        i = 1
        while i < len(parts):
            part = parts[i]
            if part.startswith("查询："):
                city = part.replace("查询：", "").strip()
                formatted_output += f"☁城市：{city}\n"
            elif part.startswith("日期："):
                date = part.replace("日期：", "").strip()
                formatted_output += f"☁日期：{date}\n"
            elif part.startswith("温度："):
                temp = part.replace("温度：", "").strip()
                formatted_output += f"☁温度：{temp}\n"
            elif part.startswith("天气："):
                weather = part.replace("天气：", "").strip()
                formatted_output += f"☁天气：{weather}\n"
            elif part.startswith("风度："):
                wind = part.replace("风度：", "").strip()
                formatted_output += f"☁风度：{wind}\n"
            elif part.startswith("空气质量："):
                air_quality = part.replace("空气质量：", "").strip()
                formatted_output += f"☁空气质量：{air_quality}\n\n"
            i += 1
        
        return formatted_output.strip()

    @filter.command("农历查询")
    async def lunar_calendar_query(self, message: AstrMessageEvent):
        """农历查询功能"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://api.yuxli.cn/api/nongli.php") as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        # 将结果按行分割，然后在一行信息后添加一个空行
                        lines = result.strip().split('\n')
                        formatted_result = '\n\n'.join(lines)
                        return CommandResult(chain=[Plain(formatted_result)])
                    else:
                        return CommandResult().error(f"获取农历信息失败，错误码：{resp.status}")
        except Exception as e:
            return CommandResult().error(f"查询农历信息时出现错误：{str(e)}")

    @filter.command("悲报")
    async def uncongrats(self, message: AstrMessageEvent):
        """悲报生成器"""
        msg = message.message_str.replace("悲报", "").strip()
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]

        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/uncongrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", 65)

        # Calculate the width and height of the text
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]

        # Calculate the starting position of the text to center it.
        x = (img.size[0] - text_width) / 2
        y = (img.size[1] - text_height) / 2

        draw.text(
            (x, y),
            msg,
            font=font,
            fill=(0, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 255),
        )

        img.save("uncongrats_result.jpg")
        return CommandResult().file_image("uncongrats_result.jpg")

    @filter.command("随机动漫图片")
    async def get_moe(self, message: AstrMessageEvent):
        """随机动漫图片"""
        shuffle = random.sample(self.moe_urls, len(self.moe_urls))
        for url in shuffle:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return CommandResult().error(f"获取图片失败: {resp.status}")
                        data = await resp.read()
                        break
            except Exception as e:
                logger.error(f"从 {url} 获取图片失败: {e}。正在尝试下一个API。")
                continue
        # 保存图片到本地
        try:
            with open("moe.jpg", "wb") as f:
                f.write(data)
            return CommandResult().file_image("moe.jpg")

        except Exception as e:
            return CommandResult().error(f"保存图片失败: {e}")

    @filter.command("搜番")
    async def get_search_anime(self, message: AstrMessageEvent):
        """以图搜番"""
        sender = message.get_sender_id()
        if sender in self.search_anmime_demand_users:
            yield message.plain_result("正在等你发图喵，请不要重复发送")
        self.search_anmime_demand_users[sender] = False
        yield message.plain_result("请在 30 喵内发送一张图片让我识别喵")
        await asyncio.sleep(30)
        if sender in self.search_anmime_demand_users:
            if self.search_anmime_demand_users[sender]:
                del self.search_anmime_demand_users[sender]
                return
            del self.search_anmime_demand_users[sender]
            yield message.plain_result("🧐你没有发送图片，搜番请求已取消了喵")

    @filter.command("mcs")
    async def mcs(self, message: AstrMessageEvent):
        """查mc服务器"""
        message_str = message.message_str
        if message_str == "mcs":
            return CommandResult().error("查 Minecraft 服务器。格式: /mcs [服务器地址]")
        ip = message_str.replace("mcs", "").strip()
        url = f"https://api.mcsrvstat.us/2/{ip}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()
                logger.info(f"获取到 {ip} 的服务器信息。")

        # result = await context.image_renderer.render_custom_template(self.mc_html_tmpl, data, return_url=True)
        motd = "查询失败"
        if (
            "motd" in data
            and isinstance(data["motd"], dict)
            and isinstance(data["motd"].get("clean"), list)
        ):
            motd_lines = [
                i.strip()
                for i in data["motd"]["clean"]
                if isinstance(i, str) and i.strip()
            ]
            motd = "\n".join(motd_lines) if motd_lines else "查询失败"

        players = "查询失败"
        version = "查询失败"
        if "error" in data:
            return CommandResult().error(f"查询失败: {data['error']}")

        name_list = []

        if "players" in data:
            players = f"{data['players']['online']}/{data['players']['max']}"

            if "list" in data["players"]:
                name_list = data["players"]["list"]

        if "version" in data:
            version = str(data["version"])

        status = "🟢" if data["online"] else "🔴"

        name_list_str = ""
        if name_list:
            name_list_str = "\n".join(name_list)
        if not name_list_str:
            name_list_str = "无玩家在线"

        result_text = (
            "【查询结果】\n"
            f"状态: {status}\n"
            f"服务器IP: {ip}\n"
            f"版本: {version}\n"
            f"MOTD: {motd}"
            f"玩家人数: {players}\n"
            f"在线玩家: \n{name_list_str}"
        )

        return CommandResult().message(result_text).use_t2i(False)

    @filter.command("原神随机图片")
    async def genshin_random_image(self, message: AstrMessageEvent):
        """原神随机图片"""
        try:
            # 设置User-Agent模拟浏览器访问
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get("http://api.xiaomei520.sbs/api/元神/?", headers=headers) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"获取图片失败: {resp.status}")
                    
                    data = await resp.read()
            
            # 保存图片到本地
            try:
                with open("genshin_image.jpg", "wb") as f:
                    f.write(data)
                return CommandResult().file_image("genshin_image.jpg")
            except Exception as e:
                return CommandResult().error(f"保存图片失败: {e}")
                
        except Exception as e:
            return CommandResult().error(f"请求失败: {e}")

    @filter.command("蔚蓝档案随机图片")
    async def blue_archive_random_image(self, message: AstrMessageEvent):
        """蔚蓝档案随机图片"""
        message_str = message.message_str.replace("蔚蓝档案随机图片", "").strip()
        
        # 检查参数
        if not message_str:
            return CommandResult().error("正确指令：蔚蓝档案随机图片 横/竖/自适应")
        
        # 验证参数
        valid_params = ["横", "竖", "自适应"]
        if message_str not in valid_params:
            return CommandResult().error("正确指令：蔚蓝档案随机图片 横/竖/自适应")
        
        # 映射参数到API参数
        param_mapping = {
            "横": "horizontal",
            "竖": "vertical", 
            "自适应": "adaptive"
        }
        
        api_param = param_mapping[message_str]
        url = f"https://rba.kanostar.top/adapt?type={api_param}"
        
        try:
            # 设置User-Agent模拟浏览器访问
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"获取图片失败: {resp.status}")
                    
                    data = await resp.read()
            
            # 保存图片到本地
            try:
                with open("blue_archive_image.jpg", "wb") as f:
                    f.write(data)
                return CommandResult().file_image("blue_archive_image.jpg")
            except Exception as e:
                return CommandResult().error(f"保存图片失败: {e}")
                
        except Exception as e:
            return CommandResult().error(f"请求失败: {e}")

    @filter.command("一言")
    async def hitokoto(self, message: AstrMessageEvent):
        """来一条一言"""
        url = "https://v1.hitokoto.cn"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()
        return CommandResult().message(data["hitokoto"] + " —— " + data["from"])

    async def save_what_eat_data(self):
        path = os.path.abspath(os.path.dirname(__file__))
        with open(path + "/resources/food.json", "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"data": self.what_to_eat_data}, ensure_ascii=False, indent=2
                )
            )

    @filter.command("今天吃什么")
    async def what_to_eat(self, message: AstrMessageEvent):
        """今天吃什么"""
        if "添加" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 添加 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error(
                    "格式：今天吃什么 添加 [食物1] [食物2] ..."
                )
            self.what_to_eat_data += l[2:]  # 添加食物
            await self.save_what_eat_data()
            return CommandResult().message("添加成功")
        elif "删除" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 删除 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error(
                    "格式：今天吃什么 删除 [食物1] [食物2] ..."
                )
            for i in l[2:]:
                if i in self.what_to_eat_data:
                    self.what_to_eat_data.remove(i)
            await self.save_what_eat_data()
            return CommandResult().message("删除成功")

        ret = f"今天吃 {random.choice(self.what_to_eat_data)}！"
        return CommandResult().message(ret)

    @filter.command("喜加一")
    async def epic_free_game(self, message: AstrMessageEvent):
        """EPIC 喜加一"""
        url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()

        games = []
        upcoming = []

        for game in data["data"]["Catalog"]["searchStore"]["elements"]:
            title = game.get("title", "未知")
            try:
                if not game.get("promotions"):
                    continue
                original_price = game["price"]["totalPrice"]["fmtPrice"][
                    "originalPrice"
                ]
                discount_price = game["price"]["totalPrice"]["fmtPrice"][
                    "discountPrice"
                ]
                promotions = game["promotions"]["promotionalOffers"]
                upcoming_promotions = game["promotions"]["upcomingPromotionalOffers"]

                if promotions:
                    promotion = promotions[0]["promotionalOffers"][0]
                else:
                    promotion = upcoming_promotions[0]["promotionalOffers"][0]
                start = promotion["startDate"]
                end = promotion["endDate"]
                # 2024-09-19T15:00:00.000Z
                start_utc8 = datetime.datetime.strptime(
                    start, "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)
                start_human = start_utc8.strftime("%Y-%m-%d %H:%M")
                end_utc8 = datetime.datetime.strptime(
                    end, "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)
                end_human = end_utc8.strftime("%Y-%m-%d %H:%M")
                discount = float(promotion["discountSetting"]["discountPercentage"])
                if discount != 0:
                    # 过滤掉不是免费的游戏
                    continue

                if promotions:
                    games.append(
                        f"【{title}】\n原价: {original_price} | 现价: {discount_price}\n活动时间: {start_human} - {end_human}"
                    )
                else:
                    upcoming.append(
                        f"【{title}】\n原价: {original_price} | 现价: {discount_price}\n活动时间: {start_human} - {end_human}"
                    )

            except BaseException as e:
                raise e
                games.append(f"处理 {title} 时出现错误")

        if len(games) == 0:
            return CommandResult().message("暂无免费游戏")
        return (
            CommandResult()
            .message(
                "【EPIC 喜加一】\n"
                + "\n\n".join(games)
                + "\n\n"
                + "【即将免费】\n"
                + "\n\n".join(upcoming)
            )
            .use_t2i(False)
        )

    @filter.command("生成奖状")
    async def generate_certificate(self, message: AstrMessageEvent):
        """在线奖状生成器"""
        # 解析参数：生成奖状 name title classname
        msg = message.message_str.replace("生成奖状", "").strip()
        parts = msg.split()
        
        if len(parts) < 3:
            return CommandResult().error("示例：生成奖状 良子 三好学生 阳光小学9年级4班")
        
        name = parts[0]
        title = parts[1]
        # classname为剩余所有部分
        classname = " ".join(parts[2:])
        
        if not classname:
            return CommandResult().error("示例：生成奖状 良子 三好学生 阳光小学9年级4班")
        
        # 检查参数长度限制
        if len(name) > 3:
            return CommandResult().error("获奖人姓名不能超过3位字符")
        if len(title) > 9:
            return CommandResult().error("奖项名不能超过9位字符")
        
        # 构建请求URL
        base_url = "https://api.pearktrue.cn/api/certcommend/"
        params = f"name={name}&title={title}&classname={classname}"
        url = f"{base_url}?{params}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("请求奖状生成API失败")
                    
                    # 检查响应内容类型
                    content_type = resp.headers.get('Content-Type', '')
                    if 'image' in content_type:
                        # 如果直接返回图片数据
                        image_data = await resp.read()
                        # 保存图片到临时文件
                        temp_path = "certificate_result.jpg"
                        with open(temp_path, "wb") as f:
                            f.write(image_data)
                        return CommandResult().file_image(temp_path)
                    else:
                        # 如果返回JSON，检查错误信息
                        try:
                            data = await resp.json()
                            if data.get("code") != 200:
                                return CommandResult().error(f"生成奖状失败：{data.get('msg', '未知错误')}")
                        except:
                            pass
                        return CommandResult().error("奖状生成API返回格式异常")
                        
        except Exception as e:
            logger.error(f"生成奖状时发生错误：{e}")
            return CommandResult().error(f"生成奖状时发生错误：{str(e)}")

    @filter.command("高铁动车车票查询")
    async def highspeed_ticket_query(self, message: AstrMessageEvent):
        """高铁动车车票查询器"""
        # 解析参数：高铁动车车票查询 出发地 终点地 查询时间（可选）
        msg = message.message_str.replace("高铁动车车票查询", "").strip()
        
        if not msg:
            return CommandResult().error("示例：高铁动车车票查询 北京 上海 2024-01-28（可选填日期，不填则查询今日）")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("示例：高铁动车车票查询 北京 上海 2024-01-28（可选填日期，不填则查询今日）")
        
        from_city = parts[0]
        to_city = parts[1]
        time_param = parts[2] if len(parts) > 2 else ""
        
        api_url = "https://api.pearktrue.cn/api/highspeedticket"
        params = f"from={urllib.parse.quote(from_city)}&to={urllib.parse.quote(to_city)}"
        if time_param:
            params += f"&time={urllib.parse.quote(time_param)}"
        url = f"{api_url}?{params}"
        
        try:
            logger.info(f"正在查询车票信息，URL：{url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    logger.info(f"API响应状态码：{resp.status}")
                    if resp.status != 200:
                        return CommandResult().error(f"查询车票信息失败，服务器状态码：{resp.status}")
                    
                    data = await resp.json()
                    logger.info(f"API返回数据：{data}")
                    
                    if data.get("code") == 200 and "data" in data and len(data["data"]) > 0:
                        # 取第一个结果
                        result = data["data"][0]
                        ticket_info = result.get("ticket_info", [{}])[0] if result.get("ticket_info") else {}
                        
                        # 构建输出结果
                        output = f"状态信息：{data.get('msg', '')}\n"
                        output += f"出发地：{data.get('from', '')}\n"
                        output += f"终点地：{data.get('to', '')}\n"
                        output += f"查询时间：{data.get('time', '')}\n"
                        output += f"获取数量：{data.get('count', '')}\n"
                        output += f"返回内容：{data.get('data', '')}\n"
                        output += f"车辆类型：{result.get('traintype', '')}\n"
                        output += f"车辆代码：{result.get('trainumber', '')}\n"
                        output += f"出发点：{result.get('departstation', '')}\n"
                        output += f"终点站：{result.get('arrivestation', '')}\n"
                        output += f"出发时间：{result.get('departtime', '')}\n"
                        output += f"到达时间：{result.get('arrivetime', '')}\n"
                        output += f"过程时间：{result.get('runtime', '')}\n"
                        output += f"车辆车票信息：{result.get('ticket_info', '')}\n"
                        output += f"座次等级：{ticket_info.get('seatname', '')}\n"
                        output += f"车票状态：{ticket_info.get('bookable', '')}\n"
                        output += f"车票价格：{ticket_info.get('seatprice', '')}\n"
                        output += f"剩余车票数量：{ticket_info.get('seatinventory', '')}"
                        
                        return CommandResult().message(output)
                    else:
                        # 如果带日期参数查询失败，尝试不带日期的查询
                        if time_param:
                            logger.info("带日期参数查询失败，尝试不带日期的查询")
                            fallback_url = f"{api_url}?from={urllib.parse.quote(from_city)}&to={urllib.parse.quote(to_city)}"
                            logger.info(f"重试URL：{fallback_url}")
                            
                            async with session.get(fallback_url) as fallback_resp:
                                if fallback_resp.status != 200:
                                    error_msg = data.get('msg', '未知错误')
                                    logger.error(f"API返回错误：code={data.get('code')}, msg={error_msg}")
                                    return CommandResult().error(f"未找到车票信息：{error_msg}")
                                
                                fallback_data = await fallback_resp.json()
                                logger.info(f"重试API返回数据：{fallback_data}")
                                
                                if fallback_data.get("code") == 200 and "data" in fallback_data and len(fallback_data["data"]) > 0:
                                    # 取第一个结果
                                    result = fallback_data["data"][0]
                                    ticket_info = result.get("ticket_info", [{}])[0] if result.get("ticket_info") else {}
                                    
                                    # 构建输出结果
                                    output = f"状态信息：{fallback_data.get('msg', '')}\n"
                                    output += f"出发地：{fallback_data.get('from', '')}\n"
                                    output += f"终点地：{fallback_data.get('to', '')}\n"
                                    output += f"查询时间：{fallback_data.get('time', '')}\n"
                                    output += f"获取数量：{fallback_data.get('count', '')}\n"
                                    output += f"返回内容：{fallback_data.get('data', '')}\n"
                                    output += f"车辆类型：{result.get('traintype', '')}\n"
                                    output += f"车辆代码：{result.get('trainumber', '')}\n"
                                    output += f"出发点：{result.get('departstation', '')}\n"
                                    output += f"终点站：{result.get('arrivestation', '')}\n"
                                    output += f"出发时间：{result.get('departtime', '')}\n"
                                    output += f"到达时间：{result.get('arrivetime', '')}\n"
                                    output += f"过程时间：{result.get('runtime', '')}\n"
                                    output += f"车辆车票信息：{result.get('ticket_info', '')}\n"
                                    output += f"座次等级：{ticket_info.get('seatname', '')}\n"
                                    output += f"车票状态：{ticket_info.get('bookable', '')}\n"
                                    output += f"车票价格：{ticket_info.get('seatprice', '')}\n"
                                    output += f"剩余车票数量：{ticket_info.get('seatinventory', '')}"
                                    
                                    return CommandResult().message(output)
                                else:
                                    error_msg = fallback_data.get('msg', '未知错误')
                                    logger.error(f"重试API返回错误：code={fallback_data.get('code')}, msg={error_msg}")
                                    return CommandResult().error(f"未找到车票信息：{error_msg}")
                        else:
                            error_msg = data.get('msg', '未知错误')
                            logger.error(f"API返回错误：code={data.get('code')}, msg={error_msg}")
                            return CommandResult().error(f"未找到车票信息：{error_msg}")
                        
        except Exception as e:
            logger.error(f"查询车票信息时发生错误：{e}")
            return CommandResult().error(f"查询车票信息时发生错误：{str(e)}")

    @filter.command("全国高校查询")
    async def college_query(self, message: AstrMessageEvent):
        """全国高校查询器"""
        # 解析参数：全国高校查询 keyword
        msg = message.message_str.replace("全国高校查询", "").strip()
        
        if not msg:
            return CommandResult().error("示例：全国高校查询 医科")
        
        keyword = msg
        api_url = "https://api.pearktrue.cn/api/college/"
        params = f"keyword={urllib.parse.quote(keyword)}"
        url = f"{api_url}?{params}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询高校信息失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data and len(data["data"]) > 0:
                        # 构建输出结果
                        output = f"状态信息：{data.get('msg', '')}\n"
                        output += f"获取数量：{data.get('count', '')}\n"
                        output += f"返回内容：\n\n"
                        
                        # 遍历所有结果
                        for i, result in enumerate(data["data"], 1):
                            output += f"=== 学校 {i} ===\n"
                            output += f"名称：{result.get('name', '')}\n"
                            output += f"部门：{result.get('department', '')}\n"
                            output += f"城市：{result.get('city', '')}\n"
                            output += f"教育等级：{result.get('level', '')}\n"
                            output += f"办学性质：{result.get('remark', '')}\n\n"
                        
                        return CommandResult().message(output)
                    else:
                        return CommandResult().error(f"未找到高校信息：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"查询高校信息时发生错误：{e}")
            return CommandResult().error(f"查询高校信息时发生错误：{str(e)}")

    @filter.command("商标信息查询")
    async def trademark_search(self, message: AstrMessageEvent):
        """商标信息查询器"""
        # 解析参数：商标信息查询 keyword
        msg = message.message_str.replace("商标信息查询", "").strip()
        
        if not msg:
            return CommandResult().error("示例：商标信息查询 光头强")
        
        keyword = msg
        api_url = "https://api.pearktrue.cn/api/trademark/"
        params = f"keyword={urllib.parse.quote(keyword)}"
        url = f"{api_url}?{params}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询商标信息失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data and len(data["data"]) > 0:
                        # 构建输出结果
                        output = f"状态信息：{data.get('msg', '')}\n"
                        output += f"搜索商标：{data.get('keyword', '')}\n"
                        output += f"返回数量：{data.get('count', '')}\n\n"
                        
                        # 遍历所有结果
                        for i, result in enumerate(data["data"], 1):
                            output += f"=== 商标 {i} ===\n"
                            output += f"注册号：{result.get('regNo', '')}\n"
                            output += f"办理机构：{result.get('agent', '')}\n"
                            output += f"注册公告日期：{result.get('regDate', '')}\n"
                            output += f"申请日期：{result.get('appDate', '')}\n"
                            output += f"商标状态：{result.get('statusStr', '')}\n"
                            output += f"国际分类值：{result.get('intCls', '')}\n"
                            output += f"国际分类名：{result.get('clsStr', '')}\n"
                            output += f"申请人名称：{result.get('applicantCn', '')}\n"
                            output += f"商标名称：{result.get('tmName', '')}\n"
                            output += f"商标图片：{result.get('tmImgOssPath', '')}\n\n"
                        
                        return CommandResult().message(output)
                    else:
                        return CommandResult().error(f"未找到商标信息：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"查询商标信息时发生错误：{e}")
            return CommandResult().error(f"查询商标信息时发生错误：{str(e)}")

    @filter.command("王者战力查询")
    async def king_glory_power_query(self, message: AstrMessageEvent):
        """王者荣耀战力查询器"""
        # 解析参数：王者战力查询 平台 英雄名称
        msg = message.message_str.replace("王者战力查询", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：王者战力查询 游戏平台（qq (安卓QQ，默认)、 wx (安卓微信)、 pqq (苹果QQ)、 pwx (苹果微信)）英雄名称\n\n示例：王者战力查询 qq 孙悟空")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("正确指令：王者战力查询 游戏平台（qq (安卓QQ，默认)、 wx (安卓微信)、 pqq (苹果QQ)、 pwx (苹果微信)）英雄名称\n\n示例：王者战力查询 qq 孙悟空")
        
        platform = parts[0].lower()
        hero_name = " ".join(parts[1:])  # 支持英雄名称包含空格
        
        # 验证平台参数
        valid_platforms = ['qq', 'wx', 'pqq', 'pwx']
        if platform not in valid_platforms:
            return CommandResult().error(f"无效的游戏平台：{platform}\n支持的平台：qq (安卓QQ，默认)、 wx (安卓微信)、 pqq (苹果QQ)、 pwx (苹果微信)")
        
        # 平台映射到新API的type参数
        platform_mapping = {
            'qq': 'aqq',  # 安卓QQ
            'wx': 'awx',  # 安卓微信
            'pqq': 'iqq', # 苹果QQ
            'pwx': 'iwx'  # 苹果微信
        }
        
        # 新API配置
        api_url = 'https://api.wzryqz.cn/gethero'
        
        # 构建请求参数
        params = {
            'hero': hero_name,
            'type': platform_mapping[platform]
        }
        
        try:
            # 设置超时和重试机制
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(api_url, params=params) as resp:
                        if resp.status != 200:
                            return CommandResult().error("查询王者战力失败，服务器返回错误状态码")
                        
                        data = await resp.json()
                        
                        if data.get("code") == 200 and "data" in data:
                            hero_data = data["data"]
                            
                            # 构建输出结果
                            output = f"英雄名称：{hero_data.get('name', '')}\n"
                            output += f"英雄ID：{hero_data.get('heroId', '')}\n"
                            output += f"英雄类型：{hero_data.get('hero_type', '')}\n"
                            output += f"游戏平台：{platform}\n"
                            output += f"前十最低战力：{hero_data.get('Top10', '')}\n"
                            output += f"前100最低战力：{hero_data.get('Top100', '')}\n"
                            
                            # 显示省标信息（前3个）
                            if 'province' in hero_data and hero_data['province']:
                                output += "\n省标战力信息：\n"
                                for i, province in enumerate(hero_data['province'][:3]):
                                    output += f"  {i+1}. {province.get('loc', '')}: {province.get('val', '')}\n"
                            
                            # 显示市标信息（前3个）
                            if 'city' in hero_data and hero_data['city']:
                                output += "\n市标战力信息：\n"
                                for i, city in enumerate(hero_data['city'][:3]):
                                    output += f"  {i+1}. {city.get('loc', '')}: {city.get('val', '')}\n"
                            
                            # 显示区标信息（前3个）
                            if 'county' in hero_data and hero_data['county']:
                                output += "\n区标战力信息：\n"
                                for i, county in enumerate(hero_data['county'][:3]):
                                    output += f"  {i+1}. {county.get('loc', '')}: {county.get('val', '')}\n"
                            
                            output += f"\n更新时间：{hero_data.get('updatetime', '')}\n"
                            
                            return CommandResult().message(output)
                        else:
                            return CommandResult().error(f"未找到英雄战力信息：{data.get('msg', '未知错误')}")
                except aiohttp.ClientError as e:
                    logger.error(f"网络连接错误：{e}")
                    return CommandResult().error("无法连接到王者战力查询服务器，请稍后重试或检查网络连接")
                except asyncio.TimeoutError:
                    logger.error("请求超时")
                    return CommandResult().error("查询超时，请稍后重试")
                        
        except Exception as e:
            logger.error(f"查询王者战力时发生错误：{e}")
            return CommandResult().error(f"查询王者战力时发生错误：{str(e)}")

    @filter.command("脑筋急转弯")
    async def brain_teaser(self, message: AstrMessageEvent):
        """脑筋急转弯生成器"""
        api_url = "https://api.pearktrue.cn/api/brainteasers/"
        
        try:
            # 设置超时
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("获取脑筋急转弯失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data:
                        question = data["data"].get("question", "")
                        answer = data["data"].get("answer", "")
                        
                        if question and answer:
                            result = f"脑筋急转弯来啦！！\n\n题目是：{question}\n\n答案：{answer}"
                            return CommandResult().message(result)
                        else:
                            return CommandResult().error("获取到的脑筋急转弯数据不完整")
                    else:
                        return CommandResult().error(f"API返回错误：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"获取脑筋急转弯时发生错误：{e}")
            return CommandResult().error(f"获取脑筋急转弯时发生错误：{str(e)}")

    @filter.regex(r"^(早安|晚安)")
    async def good_morning(self, message: AstrMessageEvent):
        """和Bot说早晚安，记录睡眠时间，培养良好作息"""
        # CREDIT: 灵感部分借鉴自：https://github.com/MinatoAquaCrews/nonebot_plugin_morning
        umo_id = message.unified_msg_origin
        user_id = message.message_obj.sender.user_id
        user_name = message.message_obj.sender.nickname
        curr_utc8 = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        curr_human = curr_utc8.strftime("%Y-%m-%d %H:%M:%S")

        # 检查CD
        if self.check_good_morning_cd(user_id, curr_utc8):
            return CommandResult().message("你刚刚已经说过早安/晚安了，请30分钟后再试喵~").use_t2i(False)

        is_night = "晚安" in message.message_str

        if umo_id in self.good_morning_data:
            umo = self.good_morning_data[umo_id]
        else:
            umo = {}
        if user_id in umo:
            user = umo[user_id]
        else:
            user = {
                "daily": {
                    "morning_time": "",
                    "night_time": "",
                }
            }

        if is_night:
            user["daily"]["night_time"] = curr_human
            user["daily"]["morning_time"] = ""  # 晚安后清空早安时间
        else:
            user["daily"]["morning_time"] = curr_human

        umo[user_id] = user
        self.good_morning_data[umo_id] = umo

        with open(f"data/{self.PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(self.good_morning_data, ensure_ascii=False, indent=2))
            
        # 更新CD
        self.update_good_morning_cd(user_id, curr_utc8)

        # 根据 day 判断今天是本群第几个睡觉的
        curr_day: int = curr_utc8.day
        curr_date_str = curr_utc8.strftime("%Y-%m-%d")

        self.invalidate_sleep_cache(umo_id, curr_date_str)
        curr_day_sleeping = 0
        for v in umo.values():
            if v["daily"]["night_time"] and not v["daily"]["morning_time"]:
                # he/she is sleeping
                user_day = datetime.datetime.strptime(
                    v["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                ).day
                if user_day == curr_day:
                    curr_day_sleeping += 1
        
        # 更新缓存为最新计算结果
        self.update_sleep_cache(umo_id, curr_date_str, curr_day_sleeping)

        if not is_night:
            # 计算睡眠时间: xx小时xx分
            sleep_duration_human = ""
            if user["daily"]["night_time"]:
                night_time = datetime.datetime.strptime(
                    user["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                )
                morning_time = datetime.datetime.strptime(
                    user["daily"]["morning_time"], "%Y-%m-%d %H:%M:%S"
                )
                sleep_duration = (morning_time - night_time).total_seconds()
                hrs = int(sleep_duration / 3600)
                mins = int((sleep_duration % 3600) / 60)
                sleep_duration_human = f"{hrs}小时{mins}分"

            return (
                CommandResult()
                .message(
                    f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
                )
                .use_t2i(False)
            )
        else:
            return (
                CommandResult()
                .message(
                    f"快睡觉喵，{user_name}！\n现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
                )
                .use_t2i(False)
            )

    @filter.command("台词搜电影")
    async def search_movie_by_lines(self, message: AstrMessageEvent):
        """通过台词搜寻存在的电影"""
        # 解析参数：台词搜电影 台词 爬取页数
        msg = message.message_str.replace("台词搜电影", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：台词搜电影 【台词】 【爬取页数】\n\n示例：台词搜电影 你还爱我吗 1")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("正确指令：台词搜电影 【台词】 【爬取页数】\n\n示例：台词搜电影 你还爱我吗 1")
        
        # 提取台词和页数
        # 台词可能包含空格，所以最后一个参数是页数，其余是台词
        page = parts[-1]
        word = " ".join(parts[:-1])
        
        # 验证页数是否为数字
        try:
            page_int = int(page)
            if page_int < 1:
                return CommandResult().error("爬取页数必须大于0")
        except ValueError:
            return CommandResult().error("爬取页数必须是数字")
        
        # API配置
        api_url = "https://api.pearktrue.cn/api/media/lines.php"
        params = {
            'word': word,
            'page': page_int
        }
        
        try:
            # 设置超时时间：连接超时10秒，总超时30秒
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.info(f"开始我的世界查询请求，参数：{params}")
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询电影信息失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data:
                        # 构建基础信息输出
                        output = f"状态信息：{data.get('msg', '')}\n"
                        output += f"台词：{data.get('word', '')}\n"
                        output += f"获取影视数量：{data.get('count', '')}\n"
                        output += f"目前页数：{data.get('now_page', '')}\n"
                        output += f"最终页数：{data.get('last_page', '')}\n"
                        output += f"返回内容：\n\n"
                        
                        # 遍历所有电影结果
                        for i, movie in enumerate(data["data"], 1):
                            output += f"=== 电影 {i} ===\n"
                            output += f"图片：{movie.get('local_img', '')}\n"
                            output += f"更新时间：{movie.get('update_time', '')}\n"
                            output += f"标题：{movie.get('title', '')}\n"
                            output += f"国家：{movie.get('area', '')}\n"
                            output += f"标签：{movie.get('tags', '')}\n"
                            output += f"导演：{movie.get('directors', '')}\n"
                            output += f"演员：{movie.get('actors', '')}\n"
                            output += f"zh_word：{movie.get('zh_word', '')}\n"
                            output += f"all_zh_word：{', '.join(movie.get('all_zh_word', []))}\n\n"
                        
                        return CommandResult().message(output)
                    else:
                        return CommandResult().error(f"未找到相关电影：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"查询电影信息时发生错误：{e}")
            return CommandResult().error(f"查询电影信息时发生错误：{str(e)}")

    @filter.command("今日运势")
    async def today_horoscope(self, message: AstrMessageEvent):
        """查询今日星座运势"""
        # 解析参数：今日运势 星座名
        msg = message.message_str.replace("今日运势", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：今日运势 星座名\n\n示例：今日运势 白羊")
        
        # 提取星座名
        constellation = msg
        
        # API配置
        api_url = "https://api.pearktrue.cn/api/xzys/"
        params = {
            'xz': constellation
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询星座运势失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data:
                        # 获取数据
                        horoscope_data = data["data"]
                        
                        # 构建基础信息输出
                        output = f"状态信息：{data.get('msg', '')}\n"
                        output += f"星座：{data.get('xz', '')}\n"
                        output += f"返回内容：\n\n"
                        
                        # 添加详细信息
                        output += f"标题：{horoscope_data.get('title', '')}\n"
                        output += f"时间：{horoscope_data.get('time', '')}\n"
                        output += f"幸运色：{horoscope_data.get('luckycolor', '')}\n"
                        output += f"幸运数字：{horoscope_data.get('luckynumber', '')}\n"
                        output += f"幸运星座：{horoscope_data.get('luckyconstellation', '')}\n"
                        output += f"简短的评论：{horoscope_data.get('shortcomment', '')}\n"
                        output += f"全文：{horoscope_data.get('alltext', '')}\n\n"
                        
                        # 添加各方面运势
                        output += f"爱情：\n{horoscope_data.get('lovetext', '')}\n\n"
                        output += f"事业：\n{horoscope_data.get('worktext', '')}\n\n"
                        output += f"金钱：\n{horoscope_data.get('moneytext', '')}\n\n"
                        output += f"健康：\n{horoscope_data.get('healthtxt', '')}"
                        
                        return CommandResult().message(output)
                    else:
                        return CommandResult().error(f"未找到星座运势：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"查询星座运势时发生错误：{e}")
            return CommandResult().error(f"查询星座运势时发生错误：{str(e)}")

    @filter.command("查询原神基本信息")
    async def genshin_basic_info(self, message: AstrMessageEvent):
        """查询原神基本信息"""
        # 解析参数：查询原神基本信息 游戏uid 所在服务器
        msg = message.message_str.replace("查询原神基本信息", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令为：查询原神基本信息 游戏uid 所在服务器\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n\n示例：/查询原神基本信息 123456 官服")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("正确指令为：查询原神基本信息 游戏uid 所在服务器\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n\n示例：/查询原神基本信息 123456 官服")
        
        # 提取UID和服务器
        uid = parts[0]
        server_name = parts[1]
        
        # 验证UID是否为数字
        try:
            uid_int = int(uid)
            if uid_int < 100000000:
                return CommandResult().error("游戏UID格式不正确")
        except ValueError:
            return CommandResult().error("游戏UID必须是数字")
        
        # 服务器名称映射
        server_mapping = {
            "官服": "cn_gf01",
            "渠道服": "cn_qd01", 
            "美洲服": "os_usa",
            "欧洲服": "os_euro",
            "亚洲服": "os_asia",
            "繁体中文服": "os_cht"
        }
        
        # 验证服务器名称
        if server_name not in server_mapping:
            return CommandResult().error("正确指令为：查询原神基本信息 游戏uid 所在服务器\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n\n示例：/查询原神基本信息 123456 官服")
        
        server_code = server_mapping[server_name]
        
        # API配置
        api_url = "https://api.nilou.moe/v1/bbs/genshin/BasicInfo"
        params = {
            'uid': uid_int,
            'server': server_code
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色详情\"否则也会查询失败！！！")
                    
                    data = await resp.json()
                    
                    # 检查API响应
                    if "data" not in data:
                        return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色详情\"否则也会查询失败！！！")
                    
                    game_data = data["data"]
                    
                    # 构建基本信息输出
                    output = "原神基本信息整理（中文）\n"
                    output += f"信息：{data.get('message', '成功')}\n"
                    output += "数据详情：\n"
                    
                    # 角色信息
                    characters = game_data.get('characters', [])
                    if characters:
                        output += "=== 角色信息 ===\n"
                        for i, char in enumerate(characters[:5], 1):  # 只显示前5个角色
                            output += f"角色{i}：{char.get('name', '')}（等级{char.get('level', '')}）\n"
                        if len(characters) > 5:
                            output += f"...还有{len(characters)-5}个角色\n"
                    
                    # 游戏统计数据
                    stats = game_data.get('stats', {})
                    if stats:
                        output += "\n=== 游戏统计数据 ===\n"
                        output += f"活跃天数：{stats.get('active_days', '')}\n"
                        output += f"成就达成数：{stats.get('achievements', '')}\n"
                        output += f"获得角色数：{stats.get('characters_number', '')}\n"
                        output += f"深境螺旋：{stats.get('spiral_abyss', '')}\n"
                    
                    # 世界探索进度
                    world_explorations = game_data.get('world_explorations', [])
                    if world_explorations:
                        output += "\n=== 世界探索进度 ===\n"
                        for exploration in world_explorations:
                            output += f"{exploration.get('name', '')}：{exploration.get('exploration_percentage', '')}%\n"
                    
                    # 尘歌壶信息
                    homes = game_data.get('homes', [])
                    if homes:
                        output += "\n=== 尘歌壶信息 ===\n"
                        for home in homes:
                            output += f"{home.get('name', '')}：等级{home.get('level', '')}，访客数{home.get('visit_num', '')}\n"
                    
                    return CommandResult().message(output)
                        
        except Exception as e:
            logger.error(f"查询原神基本信息时发生错误：{e}")
            return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色详情\"否则也会查询失败！！！")

    @filter.command("查询原神深渊信息")
    async def genshin_abyss_info(self, message: AstrMessageEvent):
        """查询原神深渊信息"""
        # 解析参数：查询原神深渊信息 游戏uid 所在服务器 深渊数据类型
        msg = message.message_str.replace("查询原神深渊信息", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令为：查询原神深渊信息 游戏uid 所在服务器 深渊数据类型\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n深渊数据类型提示：1为本期，2为上期\n\n示例：/查询原神深渊信息 123456 官服 1")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 3:
            return CommandResult().error("正确指令为：查询原神深渊信息 游戏uid 所在服务器 深渊数据类型\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n深渊数据类型提示：1为本期，2为上期\n\n示例：/查询原神深渊信息 123456 官服 1")
        
        # 提取UID、服务器和深渊数据类型
        uid = parts[0]
        server_name = parts[1]
        abyss_type = parts[2]
        
        # 验证UID是否为数字
        try:
            uid_int = int(uid)
            if uid_int < 100000000:
                return CommandResult().error("游戏UID格式不正确")
        except ValueError:
            return CommandResult().error("游戏UID必须是数字")
        
        # 服务器名称映射
        server_mapping = {
            "官服": "cn_gf01",
            "渠道服": "cn_qd01", 
            "美洲服": "os_usa",
            "欧洲服": "os_euro",
            "亚洲服": "os_asia",
            "繁体中文服": "os_cht"
        }
        
        # 验证服务器名称
        if server_name not in server_mapping:
            return CommandResult().error("正确指令为：查询原神深渊信息 游戏uid 所在服务器 深渊数据类型\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n深渊数据类型提示：1为本期，2为上期\n\n示例：/查询原神深渊信息 123456 官服 1")
        
        # 验证深渊数据类型
        if abyss_type not in ["1", "2"]:
            return CommandResult().error("正确指令为：查询原神深渊信息 游戏uid 所在服务器 深渊数据类型\n服务器有：官服 渠道服 美洲服 欧洲服 亚洲服 繁体中文服\n深渊数据类型提示：1为本期，2为上期\n\n示例：/查询原神深渊信息 123456 官服 1")
        
        server_code = server_mapping[server_name]
        abyss_type_int = int(abyss_type)
        
        # API配置
        api_url = "https://api.nilou.moe/v1/bbs/genshin/AbyssInfo"
        params = {
            'uid': uid_int,
            'server': server_code,
            'type': abyss_type_int
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色详情\"否则也会查询失败！！！")
                    
                    data = await resp.json()
                    
                    # 检查API响应
                    if "data" not in data:
                        return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色详情\"否则也会查询失败！！！")
                    
                    game_data = data["data"]
                    
                    # 构建深渊数据输出
                    output = "深境螺旋数据整理（中文）\n"
                    output += f"信息：{data.get('message', '成功')}\n"
                    output += "数据详情：\n"
                    
                    # 格式化时间戳
                    start_time = game_data.get('start_time', '')
                    end_time = game_data.get('end_time', '')
                    
                    def format_timestamp(timestamp):
                        if not timestamp:
                            return '无数据'
                        try:
                            import datetime
                            dt = datetime.datetime.fromtimestamp(int(timestamp), datetime.timezone(datetime.timedelta(hours=8)))
                            return dt.strftime('%Y 年 %m 月 %d 日 %H:%M:%S（时间戳：' + str(timestamp) + '，北京时间）')
                        except:
                            return f'时间戳：{timestamp}'
                    
                    output += f"期数 ID：{game_data.get('schedule_id', '')}\n"
                    output += f"开始时间：{format_timestamp(start_time)}\n"
                    output += f"结束时间：{format_timestamp(end_time)}\n"
                    output += f"总战斗次数：{game_data.get('total_battle_times', '')}\n"
                    output += f"总胜利次数：{game_data.get('total_win_times', '')}\n"
                    output += f"最高层数：{game_data.get('max_floor', '')}\n"
                    
                    # 处理排名数据
                    reveal_rank = game_data.get('reveal_rank', [])
                    defeat_rank = game_data.get('defeat_rank', [])
                    damage_rank = game_data.get('damage_rank', [])
                    take_damage_rank = game_data.get('take_damage_rank', [])
                    normal_skill_rank = game_data.get('normal_skill_rank', [])
                    energy_skill_rank = game_data.get('energy_skill_rank', [])
                    
                    output += f"元素爆发排名：{reveal_rank if reveal_rank else '[]（无数据）'}\n"
                    output += f"击败敌人排名：{defeat_rank if defeat_rank else '[]（无数据）'}\n"
                    output += f"造成伤害排名：{damage_rank if damage_rank else '[]（无数据）'}\n"
                    output += f"承受伤害排名：{take_damage_rank if take_damage_rank else '[]（无数据）'}\n"
                    output += f"普通攻击排名：{normal_skill_rank if normal_skill_rank else '[]（无数据）'}\n"
                    output += f"元素战技排名：{energy_skill_rank if energy_skill_rank else '[]（无数据）'}\n"
                    
                    floors = game_data.get('floors', [])
                    output += f"楼层详情：{floors if floors else '[]（无数据）'}\n"
                    output += f"总星数：{game_data.get('total_star', '')}\n"
                    output += f"已解锁：{'是' if game_data.get('is_unlock', False) else '否'}\n"
                    output += f"刚跳过的楼层：{'是' if game_data.get('is_just_skipped_floor', False) else '否'}\n"
                    output += f"跳过的楼层：{game_data.get('skipped_floor', '')}"
                    
                    return CommandResult().message(output)
                        
        except Exception as e:
            logger.error(f"查询原神深渊数据时发生错误：{e}")
            return CommandResult().error("查询失败！可能是服务器问题！\n提醒：用户必须注册米游社/HoYoLAB，且开启了\"在战绩页面是否展示角色战绩\"否则也会查询失败！！！")



    @filter.command("123网盘解析")
    async def pan123_parse(self, message: AstrMessageEvent):
        """123网盘直链解析"""
        # 解析参数：123网盘解析 链接
        msg = message.message_str.replace("123网盘解析", "").strip()
        
        # 检查是否提供了链接
        if not msg:
            return CommandResult().error("正确指令：123网盘解析 链接\n示例：123网盘解析 https://123.wq.cn")
        
        # 检查是否是有效的URL
        if not msg.startswith(("http://", "https://")):
            return CommandResult().error("正确指令：123网盘解析 链接\n示例：123网盘解析 https://123.wq.cn")
        
        # API配置
        api_url = "https://api.pearktrue.cn/api/123panparse/"
        params = {
            "url": msg,
            "pwd": "",
            "Authorization": ""
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("解析失败：服务器错误")
                    
                    data = await resp.json()
                    
                    # 检查API响应
                    if data.get("code") != 200:
                        return CommandResult().error("文件信息获取失败！！！\n可能是服务器出现问题！\n如果文件超过100mb也会出现失败！")
                    
                    # 获取解析结果
                    result_data = data.get("data", {})
                    download_url = result_data.get("downloadurl", "")
                    filename = result_data.get("filename", "未知文件")
                    size = result_data.get("size", "未知大小")
                    
                    # 构建输出结果
                    output = "解析成功！\n"
                    output += f"文件名：{filename}\n"
                    output += f"文件大小：{size}\n"
                    output += "直链链接：\n"
                    output += download_url
                    
                    return CommandResult().message(output)
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到解析服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("解析超时，请稍后重试")
        except Exception as e:
            logger.error(f"123网盘解析时发生错误：{e}")
            return CommandResult().error(f"解析失败：{str(e)}")

    @filter.command("识图")
    async def ai_image_recognition(self, message: AstrMessageEvent):
        """AI识图功能"""
        # 获取消息对象
        message_obj = message.message_obj
        
        # 查找图片对象
        image_obj = None
        for i in message_obj.message:
            if isinstance(i, Image):
                image_obj = i
                break
        
        # 如果没有找到图片，返回错误信息
        if not image_obj:
            return CommandResult().error("正确指令：识图 你发的图片")
        
        # API配置
        api_url = "https://api.pearktrue.cn/api/airecognizeimg/"
        
        try:
            # 设置超时
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 准备请求数据
                payload = {
                    "file": image_obj.url
                }
                
                async with session.post(api_url, json=payload) as resp:
                    if resp.status != 200:
                        return CommandResult().error("识图失败：服务器错误")
                    
                    data = await resp.json()
                    
                    # 检查API响应
                    if data.get("code") != 200:
                        msg = data.get("msg", "未知错误")
                        return CommandResult().error(f"识图失败：{msg}")
                    
                    # 构建输出结果
                    output = "状态信息：\n"
                    output += f"{data.get('msg', '')}\n\n"
                    output += "识别结果：\n"
                    output += f"{data.get('result', '')}"
                    
                    return CommandResult().message(output)
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到识图服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("识图超时，请稍后重试")
        except Exception as e:
            logger.error(f"AI识图时发生错误：{e}")
            return CommandResult().error(f"识图失败：{str(e)}")

    @filter.command("方舟寻访")
    async def arknights_recruitment(self, message: AstrMessageEvent):
        """明日方舟寻访模拟功能"""
        msg = message.message_str.replace("方舟寻访", "").strip()
        
        # 卡池映射
        pool_map = {
            "1": "不归花火",
            "2": "指令·重构", 
            "3": "自火中归还",
            "4": "她们渡船而来"
        }
        
        # 默认卡池为1
        pool = "1"
        if msg:
            if msg in pool_map:
                pool = msg
            else:
                return CommandResult().error(f"卡池选择错误，可选：\n1：不归花火\n2：指令·重构\n3：自火中归还\n4：她们渡船而来")
        
        # API配置 - 直接获取图片
        api_url = "https://app.zichen.zone/api/headhunts/api.php"
        params = {
            "type": "img",
            "pool": pool
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"方舟寻访失败：服务器错误 (HTTP {resp.status})")
                    
                    # 直接读取图片数据
                    image_data = await resp.read()
                    
                    # 保存图片到本地
                    try:
                        with open("arknights_recruitment.jpg", "wb") as f:
                            f.write(image_data)
                        return CommandResult().file_image("arknights_recruitment.jpg")
                    except Exception as e:
                        return CommandResult().error(f"保存图片失败: {e}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到方舟寻访服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("方舟寻访超时，请稍后重试")
        except Exception as e:
            logger.error(f"方舟寻访时发生错误：{e}")
            return CommandResult().error(f"方舟寻访失败：{str(e)}")

    @filter.command("随机游戏图片")
    async def get_random_game_image(self, message: AstrMessageEvent):
        """随机游戏图片"""
        api_url = "https://api.52vmy.cn/api/img/tu/game"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"获取游戏图片失败: {resp.status}")
                    
                    # 解析JSON响应
                    try:
                        data = await resp.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析错误：{e}")
                        return CommandResult().error("获取游戏图片失败：服务器返回了无效的JSON格式")
                    
                    # 检查API响应
                    if data.get("code") != 200:
                        msg = data.get("msg", "未知错误")
                        return CommandResult().error(f"获取游戏图片失败：{msg}")
                    
                    # 获取图片URL
                    image_url = data.get("url")
                    if not image_url:
                        return CommandResult().error("获取游戏图片失败：未获取到图片URL")
                    
                    # 下载图片
                    try:
                        async with session.get(image_url) as img_resp:
                            if img_resp.status != 200:
                                return CommandResult().error(f"下载图片失败：HTTP {img_resp.status}")
                            
                            # 读取图片数据
                            image_data = await img_resp.read()
                            
                            # 保存图片到本地
                            with open("random_game_image.jpg", "wb") as f:
                                f.write(image_data)
                            
                            return CommandResult().file_image("random_game_image.jpg")
                    
                    except Exception as e:
                        return CommandResult().error(f"下载或保存图片失败: {e}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到游戏图片服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("获取游戏图片超时，请稍后重试")
        except Exception as e:
            logger.error(f"获取游戏图片时发生错误：{e}")
            return CommandResult().error(f"获取游戏图片失败：{str(e)}")

    @filter.command("搜图")
    async def search_360_image(self, message: AstrMessageEvent):
        """360搜图功能"""
        # 获取关键词
        keyword = message.message_str.replace("搜图", "").strip()
        
        # 如果没有提供关键词，返回错误信息
        if not keyword:
            return CommandResult().error("正确指令：搜图 关键词")
        
        # API配置
        api_url = "https://api.52vmy.cn/api/img/360"
        params = {
            "msg": keyword
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"搜图失败：服务器错误 (HTTP {resp.status})")
                    
                    # 解析JSON响应
                    try:
                        data = await resp.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析错误：{e}")
                        return CommandResult().error("搜图失败：服务器返回了无效的JSON格式")
                    
                    # 检查API响应
                    if data.get("code") != 200:
                        msg = data.get("msg", "未知错误")
                        return CommandResult().error(f"搜图失败：{msg}")
                    
                    # 获取图片URL
                    if "data" not in data or "url" not in data["data"]:
                        return CommandResult().error("搜图失败：未获取到图片URL")
                    
                    image_url = data["data"]["url"]
                    
                    # 下载图片
                    try:
                        async with session.get(image_url) as img_resp:
                            if img_resp.status != 200:
                                return CommandResult().error(f"下载图片失败：HTTP {img_resp.status}")
                            
                            # 读取图片数据
                            image_data = await img_resp.read()
                            
                            # 保存图片到本地
                            with open("360_search_image.jpg", "wb") as f:
                                f.write(image_data)
                            
                            return CommandResult().file_image("360_search_image.jpg")
                    
                    except Exception as e:
                        return CommandResult().error(f"下载或保存图片失败: {e}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到搜图服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("搜图超时，请稍后重试")
        except Exception as e:
            logger.error(f"搜图时发生错误：{e}")
            return CommandResult().error(f"搜图失败：{str(e)}")



    @filter.command("葫芦侠软件搜索")
    async def huluxia_software_search(self, message: AstrMessageEvent):
        """葫芦侠软件搜索功能"""
        # 获取用户输入
        user_input = message.message_str.replace("葫芦侠软件搜索", "").strip()
        
        # 如果没有输入任何内容
        if not user_input:
            return CommandResult().error("你倒是输入内容啊！！！")
        
        # 分割输入内容
        parts = user_input.split()
        
        # 如果只有一个部分（只有软件名）
        if len(parts) == 1:
            software_name = parts[0]
            # 调用API获取软件列表
            api_url = "https://wwm.34bc.com/API/hlx_ruanjian.php"
            params = {"msg": software_name}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, params=params) as resp:
                        if resp.status != 200:
                            return CommandResult().error(f"搜索软件失败：服务器错误 (HTTP {resp.status})")
                        
                        result = await resp.text()
                        # 解析结果，格式化输出
                        lines = []
                        # 按数字分割软件信息
                        import re
                        software_items = re.split(r'\d+\.', result)
                        # 移除第一个空元素
                        if software_items and software_items[0].strip() == "":
                            software_items = software_items[1:]
                        
                        for i, item in enumerate(software_items, 1):
                            if item.strip():
                                lines.append(f"{i}号软件：{item.strip()}")
                        
                        # 添加统计信息
                        if "共搜索到" in result and "个" in result:
                            match = re.search(r'共搜索到(\d+)个', result)
                            if match:
                                total_count = match.group(1)
                                lines.append(f"\n共搜索到{total_count}个软件！！")
                        else:
                            lines.append("\n共搜索到多个软件！！")
                        
                        # 添加提示信息
                        lines.append("\n加入序号发下载链接！！")
                        
                        return CommandResult(chain=[Plain("\n".join(lines))])
                        
            except aiohttp.ClientError as e:
                logger.error(f"网络连接错误：{e}")
                return CommandResult().error("无法连接到葫芦侠软件搜索服务器，请稍后重试或检查网络连接")
            except asyncio.TimeoutError:
                logger.error("请求超时")
                return CommandResult().error("搜索软件超时，请稍后重试")
            except Exception as e:
                logger.error(f"搜索软件时发生错误：{e}")
                return CommandResult().error(f"搜索软件失败：{str(e)}")
        
        # 如果有两个部分（软件名+序号）
        elif len(parts) == 2:
            software_name = parts[0]
            try:
                sequence_number = int(parts[1])
            except ValueError:
                return CommandResult().error("正确指令：葫芦侠软件搜索 软件名 下载序号链接")
            
            # 调用API获取下载链接
            api_url = "https://wwm.34bc.com/API/hlx_ruanjian.php"
            params = {"msg": software_name, "n": str(sequence_number)}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, params=params) as resp:
                        if resp.status != 200:
                            return CommandResult().error(f"获取下载链接失败：服务器错误 (HTTP {resp.status})")
                        
                        download_link = await resp.text()
                        
                        # 检查是否是有效的下载链接
                        if download_link.startswith("http"):
                            return CommandResult(chain=[Plain(f"下载链接：\n\n{download_link}")])
                        else:
                            return CommandResult().error("获取下载链接失败：返回了无效的链接格式")
                        
            except aiohttp.ClientError as e:
                logger.error(f"网络连接错误：{e}")
                return CommandResult().error("无法连接到葫芦侠软件搜索服务器，请稍后重试或检查网络连接")
            except asyncio.TimeoutError:
                logger.error("请求超时")
                return CommandResult().error("获取下载链接超时，请稍后重试")
            except Exception as e:
                logger.error(f"获取下载链接时发生错误：{e}")
                return CommandResult().error(f"获取下载链接失败：{str(e)}")
        
        # 如果输入格式错误
        else:
            return CommandResult().error("正确指令：葫芦侠软件搜索 软件名 下载序号链接")

    @filter.command("饥荒查询")
    async def dont_starve_query(self, message: AstrMessageEvent):
        """饥荒查询功能"""
        # 获取用户输入
        user_input = message.message_str.replace("饥荒查询", "").strip()
        
        # 如果没有输入任何内容
        if not user_input:
            return CommandResult().error("正确指令：饥荒查询 物品")
        
        # 构建api请求url
        api_url = "https://api.tangdouz.com/a/jhwiki.php"
        params = {
            "nr": user_input,
            "return": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"饥荒查询失败：服务器错误 (HTTP {resp.status})")
                    
                    # 解析json响应
                    try:
                        data = await resp.json()
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析错误：{e}")
                        return CommandResult().error("饥荒查询失败：服务器返回了无效的JSON格式")
                    
                    # 获取查询内容
                    content = data.get("content", "")
                    img_url = data.get("img", "")
                    cache_time = data.get("cache_time", "")
                    
                    # 构建输出文本
                    output = f"查询内容: {content}\n\n内容修改时间：{cache_time}"
                    
                    # 如果有图片，同时发送文本和图片
                    if img_url and img_url.startswith("http"):
                        try:
                            # 下载图片
                            async with session.get(img_url) as img_resp:
                                if img_resp.status == 200:
                                    image_data = await img_resp.read()
                                    # 保存图片到本地
                                    with open("dont_starve_image.jpg", "wb") as f:
                                        f.write(image_data)
                                    # 同时发送文本和图片
                                    return CommandResult(chain=[Plain(output), Image("dont_starve_image.jpg")])
                                else:
                                    # 如果图片下载失败，返回文本信息
                                    return CommandResult(chain=[Plain(output)])
                        except Exception as e:
                            logger.error(f"下载图片失败：{e}")
                            # 如果图片下载失败，返回文本信息
                            return CommandResult(chain=[Plain(output)])
                    else:
                        # 如果没有图片，返回文本信息
                        return CommandResult(chain=[Plain(output)])
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到饥荒查询服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("饥荒查询超时，请稍后重试")
        except Exception as e:
            logger.error(f"饥荒查询时发生错误：{e}")
            return CommandResult().error(f"饥荒查询失败：{str(e)}")

    @filter.command("我的世界查询")
    async def minecraft_query(self, message: AstrMessageEvent):
        """我的世界查询功能"""
        # 获取用户输入
        user_input = message.message_str.replace("我的世界查询", "").strip()
        
        # 如果没有输入任何内容
        if not user_input:
            return CommandResult().error("正确指令：我的世界查询 物品")
        
        # 构建api请求url
        api_url = "https://api.tangdouz.com/mcwiki.php"
        params = {
            "nr": user_input,
            "return": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"我的世界查询API返回错误状态码 {resp.status}，响应内容：{error_text}")
                        return CommandResult().error(f"我的世界查询失败：服务器错误 (HTTP {resp.status})")
                    
                    # 解析json响应
                    try:
                        data = await resp.json()
                        logger.info(f"我的世界查询API响应成功，数据：{data}")
                    except json.JSONDecodeError as e:
                        logger.error(f"json解析错误：{e}")
                        return CommandResult().error("我的世界查询失败：服务器返回了无效的json格式")
                    
                    # 获取查询内容
                    allcontent = data.get("allcontent", "")
                    img_url = data.get("img", "")
                    
                    # 构建输出文本
                    output = f"查询内容: {allcontent}"
                    
                    # 如果有图片，同时发送文本和图片
                    if img_url and img_url.startswith("http"):
                        try:
                            # 下载图片
                            async with session.get(img_url) as img_resp:
                                if img_resp.status == 200:
                                    image_data = await img_resp.read()
                                    # 保存图片到本地
                                    with open("minecraft_image.jpg", "wb") as f:
                                        f.write(image_data)
                                    # 同时发送文本和图片
                                    return CommandResult(chain=[Plain(output), Image("minecraft_image.jpg")])
                                else:
                                    # 如果图片下载失败，返回文本信息
                                    return CommandResult(chain=[Plain(output)])
                        except Exception as e:
                            logger.error(f"下载图片失败：{e}")
                            # 如果图片下载失败，返回文本信息
                            return CommandResult(chain=[Plain(output)])
                    else:
                        # 如果没有图片，返回文本信息
                        return CommandResult(chain=[Plain(output)])
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到我的世界查询服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("我的世界查询超时，请稍后重试")
        except Exception as e:
            logger.error(f"我的世界查询时发生错误：{e}")
            return CommandResult().error(f"我的世界查询失败：{str(e)}")

    @filter.command("好游快爆热搜榜")
    async def haoyou_hot_search(self, message: AstrMessageEvent):
        """好游快爆热搜榜功能"""
        # API配置
        api_url = "https://wwm.34bc.com/API/Haoyou_Quick_Hot_Search.php"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return CommandResult().error(f"获取好游快爆热搜榜失败：服务器错误 (HTTP {resp.status})")
                    
                    # 获取响应文本
                    result = await resp.text()
                    
                    # 检查是否包含有效数据
                    if "----好游快爆热搜榜----" not in result:
                        return CommandResult().error("获取好游快爆热搜榜失败：服务器返回了无效数据")
                    
                    # 过滤掉PHP警告信息，只保留热搜榜内容
                    # 查找热搜榜开始标记
                    start_marker = "----好游快爆热搜榜----"
                    start_index = result.find(start_marker)
                    if start_index != -1:
                        # 从开始标记处截取内容
                        filtered_result = result[start_index:]
                        return CommandResult().message(filtered_result)
                    else:
                        return CommandResult().error("获取好游快爆热搜榜失败：数据格式异常")
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到好游快爆热搜榜服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("获取好游快爆热搜榜超时，请稍后重试")
        except Exception as e:
            logger.error(f"获取好游快爆热搜榜时发生错误：{e}")
            return CommandResult().error(f"获取好游快爆热搜榜失败：{str(e)}")

    @filter.command("AI绘画")
    async def ai_image_generation(self, message: AstrMessageEvent):
        """AI绘画功能"""
        # 获取用户输入
        user_input = message.message_str.replace("AI绘画", "").strip()
        
        # 如果没有输入任何内容
        if not user_input:
            return CommandResult().error("正确指令：AI绘画 图像描述（必填） [图像宽度] [图像高度] [提示词增强] [模型] [种子]\n\n参数说明：\n图像描述：必填，描述要生成的图像内容\n图像宽度：可选，数字，设置图像宽度\n图像高度：可选，数字，设置图像高度\n提示词增强：可选，true/false，增强提示词效果\n模型：可选，flux(默认)/kontext/turbo，选择绘画模型\n种子：可选，数字，固定种子可重现相同图像\n\n示例：AI绘画 一只狗 512 512 true flux 12345\n注意：如生成的图与描述严重不符，请使用英文提示词")
        
        # 分割输入参数
        parts = user_input.split()
        
        # 至少需要图像描述
        if len(parts) < 1:
            return CommandResult().error("正确指令：AI绘画 图像描述（必填） [图像宽度] [图像高度] [提示词增强] [模型] [种子]\n\n参数说明：\n图像描述：必填，描述要生成的图像内容\n图像宽度：可选，数字，设置图像宽度\n图像高度：可选，数字，设置图像高度\n提示词增强：可选，true/false，增强提示词效果\n模型：可选，flux(默认)/kontext/turbo，选择绘画模型\n种子：可选，数字，固定种子可重现相同图像\n\n示例：AI绘画 一只狗 512 512 true flux 12345\n注意：如生成的图与描述严重不符，请使用英文提示词")
        
        # 解析参数 - 修复参数解析逻辑
        # 查找第一个数字参数的位置（宽度参数），之前的所有内容都作为描述
        description_parts = []
        other_parts = []
        found_number = False
        
        for part in parts:
            if not found_number and part.isdigit():
                found_number = True
                other_parts.append(part)
            elif found_number:
                other_parts.append(part)
            else:
                description_parts.append(part)
        
        # 构建描述（将所有非数字部分连接起来）
        description = " ".join(description_parts)
        
        # 解析其他参数
        width = other_parts[0] if len(other_parts) > 0 else None  # 图像宽度
        height = other_parts[1] if len(other_parts) > 1 else None  # 图像高度
        enhance = other_parts[2] if len(other_parts) > 2 else None  # 提示词增强
        model = other_parts[3] if len(other_parts) > 3 else None  # 模型
        seed = other_parts[4] if len(other_parts) > 4 else None  # 种子
        
        # 构建API请求参数
        params = {"description": description}
        
        # 添加可选参数
        if width:
            try:
                # 验证宽度是否为数字
                int(width)
                params["width"] = width
            except ValueError:
                return CommandResult().error("图像宽度必须是数字")
        
        if height:
            try:
                # 验证高度是否为数字
                int(height)
                params["height"] = height
            except ValueError:
                return CommandResult().error("图像高度必须是数字")
        
        if enhance:
            if enhance in ["是", "true", "True"]:
                params["enhance"] = "true"
            elif enhance in ["不", "false", "False"]:
                params["enhance"] = "false"
            else:
                return CommandResult().error("提示词增强参数必须是：是/不")
        
        if model:
            if model in ["flux", "kontext", "turbo"]:
                params["model"] = model
            else:
                return CommandResult().error("模型参数必须是：flux/kontext/turbo")
        
        if seed:
            params["seed"] = seed
        
        # 构建API请求URL
        api_url = "https://api.lvlong.xyz/api/ai_image"
        
        try:
            # 设置超时时间：连接超时10秒，总超时180秒（AI绘画可能需要更长时间）
            timeout = aiohttp.ClientTimeout(total=180, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 记录请求开始时间
                start_time = time.time()
                logger.info(f"开始AI绘画请求，参数：{params}")
                
                async with session.get(api_url, params=params) as resp:
                    # 记录响应时间
                    response_time = time.time() - start_time
                    logger.info(f"AI绘画API响应时间：{response_time:.2f}秒，状态码：{resp.status}")
                    
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"AI绘画API返回错误状态码 {resp.status}，响应内容：{error_text}")
                        return CommandResult().error(f"AI绘画失败：服务器错误 (HTTP {resp.status})")
                    
                    # 检查响应内容类型
                    content_type = resp.headers.get('content-type', '')
                    if 'image' not in content_type:
                        error_text = await resp.text()
                        logger.error(f"AI绘画API返回了非图片内容，Content-Type: {content_type}，响应内容：{error_text}")
                        return CommandResult().error(f"AI绘画失败：服务器返回了无效的数据格式")
                    
                    # 直接读取图片数据
                    image_data = await resp.read()
                    
                    # 检查图片数据大小
                    if len(image_data) == 0:
                        logger.error("AI绘画API返回了空的图片数据")
                        return CommandResult().error("AI绘画失败：服务器返回了空的图片数据")
                    
                    logger.info(f"AI绘画成功，图片大小：{len(image_data)} 字节")
                    
                    # 保存图片到本地
                    try:
                        with open("ai_generated_image.jpg", "wb") as f:
                            f.write(image_data)
                        return CommandResult().file_image("ai_generated_image.jpg")
                    except Exception as e:
                        logger.error(f"保存AI绘画图片失败：{e}")
                        return CommandResult().error(f"保存AI绘画图片失败: {e}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到AI绘画服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("AI绘画超时，请稍后重试")
        except Exception as e:
            logger.error(f"AI绘画时发生错误：{e}")
            return CommandResult().error(f"AI绘画失败：{str(e)}")

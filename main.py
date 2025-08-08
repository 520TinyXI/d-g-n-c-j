import random
import asyncio
import os
import json
import datetime
import aiohttp
import urllib.parse
import logging
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
from astrbot.api.all import AstrMessageEvent, CommandResult, Context, Image, Plain
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

    @filter.event_message_type(filter.EventMessageType.ALL)
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
            return CommandResult().error("示例：高铁动车车票查询 北京 上海 2024-01-28")
        
        # 分割参数
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("示例：高铁动车车票查询 北京 上海 2024-01-28")
        
        from_city = parts[0]
        to_city = parts[1]
        time_param = parts[2] if len(parts) > 2 else ""
        
        api_url = "https://api.pearktrue.cn/api/highspeedticket"
        params = f"from={urllib.parse.quote(from_city)}&to={urllib.parse.quote(to_city)}"
        if time_param:
            params += f"&time={urllib.parse.quote(time_param)}"
        url = f"{api_url}?{params}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询车票信息失败")
                    
                    data = await resp.json()
                    
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
                        return CommandResult().error(f"未找到车票信息：{data.get('msg', '未知错误')}")
                        
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
        
        # API配置
        api_key = 'sSY2pUwle7dFzA4Vr6r'
        api_url = 'https://api.yaohud.cn/api/v6/wzzl'
        
        # 构建请求参数
        params = {
            'key': api_key,
            'name': hero_name,
            'lei': platform
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("查询王者战力失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data:
                        hero_data = data["data"]
                        
                        # 构建输出结果
                        output = f"英雄名称：{hero_data.get('name', '')}\n"
                        output += f"游戏平台：{hero_data.get('platform', '')}\n"
                        output += f"国标战力：{hero_data.get('guobiao', '')}\n"
                        output += f"省标地区名称：{hero_data.get('shengbiao_name', '')}\n"
                        output += f"省标最低战力：{hero_data.get('shengbiao', '')}\n"
                        output += f"市标地区名称：{hero_data.get('shibiao_name', '')}\n"
                        output += f"市标最低战力：{hero_data.get('shibiao', '')}\n"
                        output += f"区标地区名称：{hero_data.get('qubiao_name', '')}\n"
                        output += f"区标最低战力：{hero_data.get('qubiao', '')}\n"
                        output += f"更新时间：{hero_data.get('update_time', '')}\n"
                        
                        return CommandResult().message(output)
                    else:
                        return CommandResult().error(f"未找到英雄战力信息：{data.get('msg', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"查询王者战力时发生错误：{e}")
            return CommandResult().error(f"查询王者战力时发生错误：{str(e)}")

    @filter.command("脑筋急转弯")
    async def brain_teaser(self, message: AstrMessageEvent):
        """脑筋急转弯生成器"""
        api_url = "https://api.pearktrue.cn/api/brainteasers/"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("获取脑筋急转弯失败")
                    
                    data = await resp.json()
                    
                    if data.get("code") == 200 and "data" in data:
                        question = data["data"].get("question", "")
                        answer = data["data"].get("answer", "")
                        
                        if question and answer:
                            result = f"来啦来啦！\n题目是：{question}\n答案：{answer}"
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

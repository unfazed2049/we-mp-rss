from .firefox_driver import FirefoxController
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict
from core.print import print_error,print_info,print_success,print_warning
import time
import base64
import re
from datetime import datetime
from core.config import cfg
#import traceback

class WXArticleFetcher:
    """微信公众号文章获取器
    
    基于WX_API登录状态获取文章内容
    
    Attributes:
        wait_timeout: 显式等待超时时间(秒)
    """
    
    def __init__(self, wait_timeout: int = 3):
        """初始化文章获取器"""
        self.wait_timeout = wait_timeout
        self.controller = FirefoxController()
        if not self.controller:
            raise Exception("WebDriver未初始化或未登录")
    
    def convert_publish_time_to_timestamp(self, publish_time_str: str) -> int:
        """将发布时间字符串转换为时间戳
        
        Args:
            publish_time_str: 发布时间字符串，如 "2024-01-01" 或 "2024-01-01 12:30"
            
        Returns:
            时间戳（秒）
        """
        try:
            # 尝试解析不同的时间格式
            formats = [
                "%Y-%m-%d %H:%M:%S",  # 2024-01-01 12:30:45
                "%Y年%m月%d日 %H:%M",        # 2024年03月24日 17:14
                "%Y-%m-%d %H:%M",     # 2024-01-01 12:30
                "%Y-%m-%d",           # 2024-01-01
                "%Y年%m月%d日",        # 2024年01月01日
                "%m月%d日",            # 01月01日 (当年)
            ]
            
            for fmt in formats:
                try:
                    if fmt == "%m月%d日":
                        # 对于只有月日的格式，添加当前年份
                        current_year = datetime.now().year
                        full_time_str = f"{current_year}年{publish_time_str}"
                        dt = datetime.strptime(full_time_str, "%Y年%m月%d日")
                    else:
                        dt = datetime.strptime(publish_time_str, fmt)
                    return int(dt.timestamp())
                except ValueError:
                    continue
            
            # 如果所有格式都失败，返回当前时间戳
            print_warning(f"无法解析时间格式: {publish_time_str}，使用当前时间")
            return int(datetime.now().timestamp())
            
        except Exception as e:
            print_error(f"时间转换失败: {e}")
            return int(datetime.now().timestamp())
       
        
    def extract_biz_from_source(self,url:str) -> str:
        """从URL或页面源码中提取biz参数
        
        1. 首先尝试从URL参数中提取__biz
        2. 如果URL中没有，则从页面源码中提取
        """
        # 尝试从URL中提取
        match = re.search(r'[?&]__biz=([^&]+)', url)
        if match:
            return match.group(1)
            
        # 从页面源码中提取
        try:
            # 从页面源码中查找biz信息
            page_source = self.driver.page_source
            print_info(f'开始解析Biz')
            biz_match = re.search(r'var biz = "([^"]+)"', page_source)
            if biz_match:
                return biz_match.group(1)
                
            # 尝试其他可能的biz存储位置
            biz_match = re.search(r'window\.__biz=([^&]+)', page_source)
            if biz_match:
                return biz_match.group(1)

            biz_match = self.driver.execute_script('return window.biz')
            if biz_match:
                return biz_match
                
            return ""
            
        except Exception as e:
            print_error(f"从页面源码中提取biz参数失败: {e}")
            return ""
    def extract_id_from_url(self,url:str) -> str:
        """从微信文章URL中提取ID"""
        # 从URL中提取ID部分
        match = re.search(r'/s/([A-Za-z0-9_-]+)', url)
        if not match:
            return None
        id_str = match.group(1)
          # 添加必要的填充
        padding = 4 - len(id_str) % 4
        if padding != 4:
            id_str += '=' * padding
        try:
            # 解码base64
            id_number = base64.b64decode(id_str).decode("utf-8")
            return id_number
        except Exception as e:
            pass
        return id_str  
    def FixArticle(self,urls:list=None,mp_id:str=None):
        # 示例用法
        try:
            from jobs.article import UpdateArticle
            from core.models.article import Article
            # fetch_articles_without_content()
            urls=[
                "https://mp.weixin.qq.com/s/YTHUfxzWCjSRnfElEkL2Xg",
            ] if urls is None else urls
            for url in urls:
                article_data = Web.get_article_content(url)
                # 将 article_data 转换为 Article 对象
                # 从URL中提取ID并转换为数字
                article = {                
                    "id":article_data.get('id'), 
                    "title":article_data.get('title'),
                    "mp_id":article_data.get('mp_id') if mp_id is None else mp_id, 
                    "publish_time":article_data.get('publish_time'),
                    "pic_url":article_data.get('pic_url'),
                    "content":article_data.get('content'),
                    "url":url,
                }
                del article_data['content']
                print_success(article_data)
                ok=UpdateArticle(article,check_exist=True)
                if ok:
                    print_info(f"已更新文章: {article_data['title']}")
                time.sleep(3)  # 避免请求过快
            self.Close()
        except Exception as e:
            print_error(f"错误: {e}") 
    def get_article_content(self, url: str) -> Dict:
        """获取单篇文章详细内容
        
        Args:
            url: 文章URL (如: https://mp.weixin.qq.com/s/qfe2F6Dcw-uPXW_XW7UAIg)
            
        Returns:
            文章内容数据字典，包含:
            - title: 文章标题
            - author: 作者
            - publish_time: 发布时间
            - content: 正文HTML
            - images: 图片URL列表
            
        Raises:
            Exception: 如果未登录或获取内容失败
        """
        info={
                "id": self.extract_id_from_url(url),
                "title": "",
                "publish_time": "",
                "content": "",
                "images": "",
                "mp_info":{
                "mp_name":"",   
                "logo":"",
                "biz": "",
                }
            }
        self.controller.start_browser(mobile_mode=True,dis_image=True)    

        self.driver = self.controller.driver
        print_warning(f"Get:{url} Wait:{self.wait_timeout}")
        self.controller.open_url(url)
        driver=self.driver
        wait = WebDriverWait(driver, self.wait_timeout)
        try:
           
            driver.get(url)
              # 等待页面加载
            body=driver.find_element(By.TAG_NAME,"body").text
            info["content"]=body
            if "该内容已被发布者删除" in body or "The content has been deleted by the author." in body:
                info["content"]="DELETED"
                raise Exception("该内容已被发布者删除")
            if  "内容审核中" in body:
                info['content']="DELETED"
                raise Exception("内容审核中")
            if "该内容暂时无法查看" in body:
                info["content"]="DELETED"
                raise Exception("该内容暂时无法查看")
            if "违规无法查看" in body:
                info["content"]="DELETED"
                raise Exception("违规无法查看")
            if "发送失败无法查看" in body:
                info["content"]="DELETED"
                raise Exception("发送失败无法查看")
            if "Unable to view this content because it violates regulation" in body:     
                info["content"]="DELETED"
                raise Exception("违规无法查看")
            # 等待关键元素加载
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#js_article"))
            )
            # print(body)
             # 等待页面加载完成，并查找 meta[property="og:title"]
            og_title = wait.until(EC.presence_of_element_located((By.XPATH, '//meta[@property="og:title"]')))
            
            # 获取属性值
            # print(og_title.get_attribute("content"))
            # 获取文章元数据
            title = og_title.get_attribute("content")
            self.export_to_pdf(f"./data/{title}.pdf")
            author = driver.find_element(
                By.XPATH, '//meta[@property="og:article:author"]'
            ).get_attribute('content').strip()
            
            publish_time_str = driver.find_element(
                By.CSS_SELECTOR, "#publish_time"
            ).text.strip()
            
            # 将发布时间转换为时间戳
            publish_time = self.convert_publish_time_to_timestamp(publish_time_str)
            
            # 获取正文内容和图片
            content_element = driver.find_element(
                By.CSS_SELECTOR, "#js_content"
            )
            content = content_element.get_attribute("innerHTML")
            
            images = [
                img.get_attribute("data-src") or img.get_attribute("src")
                for img in content_element.find_elements(By.TAG_NAME, "img")
                if img.get_attribute("data-src") or img.get_attribute("src")
            ]
            if images and len(images)>0:
                info["pic_url"]=images[0]
            info["title"]=title
            info["author"]=author
            info["publish_time"]=publish_time
            info["content"]=content
            info["images"]=images

        except Exception as e:
            # raise Exception(f"文章内容获取失败: {str(e)}")
            print(f"文章内容获取失败: {str(e)}")
            print_warning(f"\n\n{body}")
            #traceback.print_exc()
            # raise

        try:
            # 等待关键元素加载
            #ele_logo =wait.until(
            #    EC.presence_of_element_located((By.CLASS_NAME, "wx_follow_avatar"))
            #)
            # 获取<img>标签的src属性
            #logo_src = ele_logo.find_element(By.TAG_NAME, 'img').get_attribute('src')
            logo_xpath = "//span[@class='wx_follow_avatar'][1]/img"
            wait.until(
                lambda driver: driver.find_element(By.XPATH, logo_xpath).get_attribute('src')
                and not driver.find_element(By.XPATH, logo_xpath).get_attribute('src').startswith('data:image')
            )

            logo_src = driver.find_element(By.XPATH, logo_xpath).get_attribute('src')

            # ele_name=driver.find_element((By.CLASS_NAME, "js_wx_follow_nickname"))
            #title=driver.execute_script('return $("#js_wx_follow_nickname").text()')
            # title= ele_name.text
            title_elem = wait.until(
                EC.presence_of_element_located((By.ID, "js_wx_follow_nickname"))
            )
            title = title_elem.text
            
            info["mp_info"]={
                "mp_name":title,
                "logo":logo_src,
                "biz": self.extract_biz_from_source(url), 
            }
            info["mp_id"]= "MP_WXS_"+base64.b64decode(info["mp_info"]["biz"]).decode("utf-8")
        except Exception as e:
            print_error(f"获取公众号信息失败: {str(e)}")   
            #traceback.print_exc()
            pass
        self.Close()
        return info
    def Close(self):
        """关闭浏览器"""
        if hasattr(self, 'controller'):
            self.controller.Close()
        else:
            print("WXArticleFetcher未初始化或已销毁")
    def __del__(self):
        """销毁文章获取器"""
        if hasattr(WXArticleFetcher, 'controller'):
            WXArticleFetcher.controller.close()

    def export_to_pdf(self, title=None):
        """将文章内容导出为 PDF 文件
        
        Args:
            output_path: 输出 PDF 文件的路径（可选）
        """
        try:
            if cfg.get("export.pdf.enable",False)==False:
                return
            # 使用浏览器打印功能生成 PDF
            if output_path:
                import os
                pdf_path=cfg.get("export.pdf.dir","./data/pdf")
                output_path=os.path.abspath(f"{pdf_path}/{title}.pdf")
                self.driver.execute_script(f"window.print({{'printBackground': true, 'destination': 'save-as-pdf', 'outputPath': '{output_path}'}});")
                time.sleep(3)
            print_success(f"PDF 文件已生成{output_path}")
        except Exception as e:
            print_error(f"生成 PDF 失败: {str(e)}")

    
Web=WXArticleFetcher()
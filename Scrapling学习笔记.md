

## 1. 项目概述

Scrapling 是一个**自适应 Web 抓取框架**，能处理从单次 HTTP 请求到大规模并发爬取的全部场景。它的三大核心优势：

| 特性             | 描述                                          |
| -------------- | ------------------------------------------- |
| 🧠 **自适应解析**   | 解析器会学习网站变化规律，页面更新后自动重新定位元素                  |
| 🛡️ **反爬绕过**   | 内置 Cloudflare Turnstile 绕过、TLS 指纹模拟、真实浏览器模拟 |
| 🕷️ **完整爬虫框架** | 支持并发、多会话、暂停/恢复、流式处理的 Scrapy-like 爬虫系统       |

### 设计哲学

Scrapling 遵循**渐进增强**原则：
- 简单静态页面 → 使用轻量 `Fetcher`
- 需要 JavaScript → 使用 `DynamicFetcher`
- 面对反爬保护 → 使用 `StealthyFetcher`
- 规模化爬取 → 使用 `Spider` 框架

所有获取器都返回统一的 `Response` 对象，解析逻辑完全复用。

---

## 3. 核心架构

```
Scrapling 整体架构
│
├── 解析层（Parser）
│   ├── Selector         - 核心 HTML 解析引擎（基于 lxml）
│   └── AutoScraper      - 自适应存储与重定位
│
├── 获取层（Fetchers）
│   ├── Fetcher          - 轻量级 HTTP（基于 curl_cffi）
│   ├── DynamicFetcher   - 浏览器自动化（基于 Playwright Chromium/Chrome）
│   ├── StealthyFetcher  - 高级隐身（基于 patchright + Playwright）
│   └── ProxyRotator     - 代理轮换器
│
└── 爬虫层（Spiders）
    ├── Spider           - 并发爬虫框架（类 Scrapy API）
    ├── Request          - 请求对象
    ├── Response         - 响应对象（继承自 Selector）
    └── SessionManager   - 多会话管理
```

---

## 4. 解析器（Parser）

### 4.1 Selector 类

`Selector` 是 Scrapling 的核心解析引擎，位于 `scrapling.parser`，封装了 `lxml.html.HtmlElement`。

```python
from scrapling.parser import Selector

# 直接解析 HTML 字符串
page = Selector("<html><body><h1>Hello</h1></body></html>")

# 完整参数
page = Selector(
    content="<html>...</html>",   # HTML 内容
    url="https://example.com",     # 基础 URL（用于解析相对链接）
    encoding="utf-8",              # 编码，默认 utf-8
    huge_tree=True,                # 启用大型文档解析
    keep_comments=False,           # 是否保留 HTML 注释
    keep_cdata=False,              # 是否保留 CDATA
    adaptive=False,                # 是否启用自适应模式
    storage=None,                  # 自定义存储系统（默认 SQLite）
)
```

这是 Scrapling 的"解析器工厂"，用于把一段 HTML 代码变成可以查询的对象。就像把原材料（HTML字符串）放进加工机器，得到一个便于操作的零件。content 参数是最核心的，url 参数用于处理相对链接（比如图片 src="./logo.png" 会自动补全成完整网址），其他参数一般保持默认即可。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `content` | str/bytes | None | 要解析的 HTML 内容 |
| `url` | str | `""` | 基础 URL，用于解析相对 URL |
| `encoding` | str | `"utf-8"` | 字符编码 |
| `huge_tree` | bool | `True` | 启用大型 HTML 文档解析 |
| `keep_comments` | bool | `False` | 保留 HTML 注释 |
| `keep_cdata` | bool | `False` | 保留 CDATA 部分 |
| `adaptive` | bool | `False` | 启用自适应元素跟踪 |
| `storage` | StorageSystemMixin | SQLiteStorageSystem | 存储后端 |

### 4.2 选择元素的方法

#### CSS 选择器

```python
# 选择元素（返回 Selectors 集合）
items = page.css('.product')
items = page.css('div.quote')
```

> **💡 通俗理解**：就像在超市货架上找商品——`.product` 查找所有带 "product" 标签的东西，`div.quote` 查找所有"引用块"样式的 `<div>` 标签。无论页面上有多少个匹配项，都会返回。
>
> **实例**：如果网页是一本书，`page.css('h2')` 就是把所有"二级标题"都挑出来。

# 提取文本（::text 伪元素）
text = page.css('h1::text').get()          # 获取第一个
texts = page.css('h1::text').getall()       # 获取所有

> **💡 通俗理解**：`::text` 就像撕掉标签只看里面的文字。比如商品卡片里写了"¥99"，用这个就能只拿到"¥99"，而不会拿到 `<span>¥99</span>` 这种标签代码。
>
> **实例**：抓取新闻标题、书籍名称、商品价格等纯文字内容时用这个。

# 提取属性值（::attr() 伪元素）
href = page.css('a::attr(href)').get()
hrefs = page.css('a::attr(href)').getall()

> **💡 通俗理解**：属性就是 HTML 标签里的"元数据"。比如链接 `<a href="https://...">`，"href" 就是属性名，`::attr(href)` 就是取出这个网址。
>
> **实例**：批量提取所有商品详情页的链接、下载所有图片的 src 地址、获取按钮的 onclick 跳转地址等。

# 嵌套选择
for item in page.css('.quote'):
    text = item.css('.text::text').get()
    author = item.css('.author::text').get()

> **💡 通俗理解**：先定位一个"大盒子"（如每条评论），再在里面找"小零件"（如评论内容和作者）。就像先找出一本书的每一章，再从每章里找出标题和作者。
>
> **实例**：抓取论坛帖子列表时，先定位每个帖子块，再分别提取标题、作者、发布时间、内容。

#### XPath 选择器

```python
# 基础 XPath
items = page.xpath('//div[@class="quote"]')

# 获取文本
text = page.xpath('//h1/text()').get()

# 获取属性
href = page.xpath('//a/@href').get()

# 带变量绑定
result = page.xpath('//div[@id=$id]', id='product-1')
```

这是另一种查找元素的方式，比 CSS 选择器更强大但语法更复杂。XPath 像是在地图上描述路径，比如 "//div[@class='quote']" 表示"从根目录开始找所有 class 为 quote 的 div"。适合需要精确描述元素位置的场景，比如"找第三个兄弟节点"或"包含特定文本的元素"。

#### BeautifulSoup 风格（find/find_all）

```python
# 按标签名查找
page.find_all('div')
page.find_all(['div', 'span'])    # 多标签

# 按属性查找
page.find_all('div', class_='quote')
page.find_all('a', href=True)           # 有 href 属性即可

# 字典形式
page.find_all({'class': 'quote'})

# 属性模式匹配
page.find_all({'href$': 'Einstein'})    # href 以 'Einstein' 结尾
page.find_all({'href*': '/author/'})    # href 包含 '/author/'

# 使用函数过滤
page.find_all(lambda e: "world" in e.css('.text::text').get())

# 组合多条件
page.find_all('div', {'class': 'quote'}, lambda e: "world" in e.text)

# 等效的 find（只返回第一个）
element = page.find('div', class_='quote')
```

如果你用过 BeautifulSoup，应该很快上手。这里的 find_all 就像"找出所有满足条件的盒子"，可以按标签名、class、id、甚至用函数自定义条件。字典形式用得比较多，{'href$': 'xxx'} 表示"href 属性以 xxx 结尾"，适合匹配特定格式的链接。

#### 按文本内容查找

```python
# 精确匹配
element = page.find_by_text('Tipping the Velvet')

# 部分匹配
elements = page.find_by_text('the', partial=True, first_match=False)

# 区分大小写
elements = page.find_by_text('The', case_sensitive=True)

# 参数说明
page.find_by_text(
    text='query',           # 要匹配的文本（必填）
    first_match=True,       # True=只返回第一个
    case_sensitive=False,   # False=不区分大小写
    clean_match=False,      # True=清理空白后再匹配
    partial=False,          # True=部分匹配
)
```

有时候不知道元素的 class 或标签，只知道里面写了什么字。比如想找"登录"按钮，但不确定它是 a 标签还是 button，用这个方法最方便。partial=True 表示包含这段文字就行，case_sensitive=False 表示不区分大小写。

#### 按正则表达式查找

```python
import re

# 传入正则字符串
elements = page.find_by_regex(r'£[\d\.]+')

# 传入编译后的 Pattern
regex = re.compile(r'£[\d\.]+')
elements = page.find_by_regex(regex)
```

当你需要找"符合某种模式"的内容时用这个。比如网页上有很多价格，像 £51.77、£53.74，用正则 r'£[\d\.]+' 就能一次性把"英镑符号+数字+小数点"的模式全部匹配出来。先编译再使用效率更高，适合多次匹配同一个模式。

#### 查找相似元素

```python
# 找到一个参考元素
first_item = page.find_by_text('Tipping the Velvet')

# 自动查找所有相似元素（特别适合列表项）
similar_elements = first_item.find_similar()

# 带参数
similar_elements = first_item.find_similar(
    similarity_threshold=0.2,              # 相似度阈值（0-1）
    ignore_attributes=('href', 'src'),     # 忽略的属性
    match_text=False,                      # 是否考虑文本内容
)
```

这个功能很智能——找到第一个元素后，它能自动发现结构相似的其他元素。比如网页是一个商品列表，结构和样式都一样，只要告诉它"第一个商品的卡片"，它就能把所有商品卡片都找出来。threshold 越低越宽松，ignore_attributes 用于忽略经常变化的属性（如链接地址）。

#### 正则提取 (re / re_first)

```python
# 从所有匹配元素中提取
prices = page.css('.price_color').re(r'[\d\.]+')
# 返回: ['51.77', '53.74', '50.10', ...]

# 提取第一个
price = page.css('.price_color')[0].re_first(r'[\d\.]+')
# 返回: '51.77'

# 提取分组
links = page.css('a::attr(href)').re(r'catalogue/(.*)/index.html')
```

从已选中的元素内容中提取特定模式的数据。假设选中了价格元素，内容是 "£51.77"，用 re(r'[\d\.]+') 就能只提取 "51.77" 这个数字部分。re 返回所有匹配，re_first 只返回第一个，括号可以捕获特定的分组部分。

#### 生成选择器

```python
element = page.find({'href*': '/author/'})

# 短选择器（尽可能简洁）
print(element.generate_css_selector)         # 'body > div > ...'
print(element.generate_xpath_selector)       # '//body/div/...'

# 完整选择器（从根部开始）
print(element.generate_full_css_selector)
print(element.generate_full_xpath_selector)
```

有时候需要知道"这个元素是怎么被找到的"，这个方法可以生成对应的选择器字符串。比如调试代码时发现某个元素选不到了，可以先生成选择器看看路径对不对。短选择器尽量精简，完整选择器从 html 根元素开始描述。

### 4.3 DOM 导航

```python
element = page.css('.product')[0]

# 父元素
parent = element.parent

# 子元素（所有直接子节点）
children = element.children

# 兄弟元素（父元素的其他子节点）
siblings = element.siblings

# 相邻元素
next_elem = element.next          # 下一个兄弟
prev_elem = element.previous      # 上一个兄弟

# 祖先遍历（生成器）
for ancestor in element.iter_ancestors():
    print(ancestor.tag)
```

找到元素后，可以在 DOM 树里上下左右移动。parent 找父级，children 找直接子级，siblings 找同一层级的其他元素，next/previous 找上下相邻的兄弟。iter_ancestors 沿着祖先链往上遍历，比如从 span 标签一直找到 body 和 html。

### 4.4 数据提取

#### 元素属性

```python
element = page.css('.product')[0]

print(element.tag)              # 标签名，如 'div'
print(element.text)             # 直接文本内容（TextHandler 类型）
print(element.attrib)           # 属性字典（AttributesHandler 类型）
print(element.html_content)     # 元素外部 HTML 字符串
print(element.get_all_text())   # 递归获取所有文本内容
```

选中一个元素后，这些属性帮你了解它的信息。tag 是标签名（div/span/a 等），text 是里面的文字，attrib 是所有属性（像字典一样可以用 .get() 取值），html_content 是包含标签的完整 HTML 字符串，get_all_text 会把子元素里的文字也收集起来。

#### TextHandler 扩展方法

```python
text = element.css('h1::text').get()

# 清理空白
clean_text = text.clean()

# 正则匹配
matches = text.re(r'\d+')

# JSON 解析
data = text.json()
```

提取出来的文字不是普通字符串，而是特殊的 TextHandler 对象，支持更多操作。clean() 去掉多余空格和换行，re() 在文字里找匹配模式，json() 直接把 JSON 格式的字符串转成 Python 对象（比如 API 返回的数据直接嵌入在 HTML 里时很有用）。

#### AttributesHandler 扩展方法

```python
attribs = element.attrib

# 类字典访问
print(attribs['class'])
print(attribs.get('id', 'default'))

# 搜索属性值
results = attribs.search_values('active')

# 转为 JSON 字符串
json_str = attribs.json_string()
```

属性对象也提供了扩展功能。search_values('active') 可以在属性值里搜索包含 "active" 的内容，比如 class="btn btn-active" 就能匹配上。json_string() 把所有属性转成 JSON 格式，方便调试或保存到文件。

#### Selectors 集合操作

```python
items = page.css('.product')    # Selectors 类型

# 批量提取
texts = items.css('h2::text').getall()    # 对每个元素应用选择器
hrefs = items.css('a::attr(href)').getall()

# 过滤集合
filtered = items.filter(lambda e: 'sale' in e.attrib.get('class', ''))

# 获取第一个
first = items.get()     # 等同于 items[0]（安全，不存在返回 None）
```

选中多个元素后，可以继续对集合操作。items.css('h2::text').getall() 会对每个商品卡片提取标题，等于一个循环提取。filter() 用函数过滤，比如只保留 class 里包含 "sale" 的元素。get() 比 [0] 更安全，找不到元素时不会报错。

### 4.5 自适应抓取

自适应抓取是 Scrapling 的核心特色功能，可以在**网站结构变化后**自动重新定位元素。

#### 工作原理

分为两个阶段：

1. **保存阶段**：将元素的唯一属性（标签名、文本、属性、兄弟元素、父元素信息）存入 SQLite 数据库
2. **匹配阶段**：当原始选择器无法找到元素时，基于相似度算法在页面中查找最匹配的元素

#### 基本使用

**第一步：首次选择时保存元素**
```python
from scrapling.fetchers import Fetcher

page = Fetcher.get('https://example.com')

# 使用 auto_save=True 保存选择结果
products = page.css('.product', auto_save=True)
```

**第二步：网站结构变化后重新查找**
```python
# 网站改版后，使用 adaptive=True 智能定位
products = page.css('.product', adaptive=True)
```

这是 Scrapling 的核心功能——让爬虫"记住"要抓的元素。第一次运行加 auto_save，系统会记录每个元素的样子（标签、位置、文字、周围元素等）；网站改版后用 adaptive，系统会智能匹配最像的那个。相当于给爬虫装了个"人脸识别"，即使元素换了位置也能找到。

#### 全局启用自适应

```python
# 方式一：Selector 类
page = Selector(page_source, adaptive=True, url='example.com')

# 方式二：Fetcher 全局设置
Fetcher.configure(adaptive=True)
page = Fetcher.get('https://example.com')
page.products = page.css('.product', auto_save=True)
```

不想每次都传参数？可以全局配置。用 Fetcher.configure() 设置后，这个 Fetcher 实例的所有请求都会默认启用自适应。适合写好一个爬虫后持续运行的情况，不用每次调用都记着加参数。

#### 手动模式（自定义标识符）

```python
# 1. 通过文本或其他方式找到元素
element = page.find_by_text('特定产品名称', first_match=True)

# 2. 手动保存，指定唯一标识符
page.save(element, 'my_special_product')

# 3. 后续在变化的网站上重新定位
element_dict = page.retrieve('my_special_product')
element = page.relocate(element_dict, selector_type=True)
```

自动保存有时候保存的位置不对，可以手动控制。给要保存的元素起个名字（比如 'my_special_product'），后续用这个名字就能找回。retrieve 获取保存的信息，relocate 根据这些信息重新定位。适合需要精确控制保存哪个元素的场景。

#### 跨域自适应（同一网站不同 URL）

```python
from scrapling import Fetcher

old_url = "https://web.archive.org/web/20100102003420/http://stackoverflow.com/"
new_url = "https://stackoverflow.com/"
selector = '#hmenus > div:nth-child(1) > ul > li:nth-child(1) > a'

# 配置跨域自适应（指定统一的域名）
Fetcher.configure(adaptive=True, adaptive_domain='stackoverflow.com')

# 旧版页面：保存元素
page_old = Fetcher.get(old_url, timeout=30)
element_old = page_old.css(selector, auto_save=True)[0]

# 新版页面：智能定位
page_new = Fetcher.get(new_url)
element_new = page_new.css(selector, adaptive=True)[0]

print(element_old.text == element_new.text)  # True
```

这个功能用于抓取同一网站的不同版本。比如想对比网站改版前后的某个元素，或者从网页存档（web.archive.org）恢复历史数据，只要指定域名就能跨 URL 共享保存的信息。adaptive_domain 告诉系统这些 URL 属于同一个网站。

#### 自适应功能的关键参数

| 参数 | 说明 |
|------|------|
| `adaptive=True` | 启用自适应匹配（失败时从数据库查找相似元素） |
| `auto_save=True` | 自动保存选择结果到数据库 |
| `adaptive_domain` | 跨域保存/使用自适应数据（不同 URL 但同一网站） |
| `storage` | 自定义存储系统（默认 SQLite） |
| `identifier` | 元素的自定义标识符 |

> ⚠️ **注意**：自适应保存时只保存选择结果中**第一个元素**的属性。

---

## 5. 获取器（Fetchers）

### 5.1 如何选择 Fetcher

```
需要执行 JS / 动态内容？
    ├── 否 → Fetcher（最快、最轻量）
    └── 是 → 有反爬保护？
              ├── 否 → DynamicFetcher（Playwright 自动化）
              └── 是 → StealthyFetcher（高级隐身）
```

| Fetcher | 适用场景 | 速度 | 隐身能力 |
|---------|----------|------|----------|
| `Fetcher` | 静态页面、API | ⚡⚡⚡⚡ | ★★☆☆ |
| `DynamicFetcher` | JS 渲染、SPA | ⚡⚡ | ★★★☆ |
| `StealthyFetcher` | Cloudflare、反爬 | ⚡ | ★★★★ |

### 5.2 Fetcher（静态 HTTP 请求）

基于高性能 `curl_cffi` 库，支持 TLS 指纹模拟和 HTTP/3。

#### 基础使用

```python
from scrapling.fetchers import Fetcher

# GET 请求
page = Fetcher.get('https://quotes.toscrape.com/')

# POST 请求（表单）
page = Fetcher.post('https://example.com/login', data={'user': 'u', 'pass': 'p'})

# POST 请求（JSON）
page = Fetcher.post('https://api.example.com', json={'key': 'value'})

# PUT 请求
page = Fetcher.put('https://example.com/update', data={'status': 'updated'})

# DELETE 请求
page = Fetcher.delete('https://example.com/resource/123')

# 获取 JSON API
page = Fetcher.get('https://api.github.com/events')
data = page.json()
```

这是最常用的抓取方式。Fetcher 就像一个轻量级的网络请求工具，get 是读取网页，post 是提交数据（登录、表单），json() 把 API 返回的 JSON 数据直接转成 Python 字典。适合不需要 JavaScript 渲染的静态页面和 API 接口，速度很快。

#### 完整参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | str | 必填 | 目标 URL |
| `stealthy_headers` | bool | `True` | 自动生成真实浏览器请求头 |
| `follow_redirects` | bool/str | `"safe"` | 重定向控制（`"safe"` 防 SSRF） |
| `timeout` | int | `30` | 超时秒数 |
| `retries` | int | `3` | 失败重试次数 |
| `retry_delay` | int | `1` | 重试间隔秒数 |
| `impersonate` | str/list | None | 模拟浏览器 TLS 指纹 |
| `http3` | bool | `False` | 启用 HTTP/3 协议 |
| `cookies` | dict/list | None | 请求 Cookie |
| `proxy` | str | None | 代理（格式：`http://user:pass@host:port`） |
| `proxies` | dict | None | 多协议代理 `{"http": url, "https": url}` |
| `proxy_rotator` | ProxyRotator | None | 自动代理轮换实例 |
| `headers` | dict | None | 自定义请求头 |
| `verify` | bool | `True` | 验证 HTTPS 证书 |
| `auth` | tuple | None | 基础认证 `(user, pass)` |
| `params` | dict | None | URL 查询参数 |

#### 可模拟的浏览器

```
"edge"、"chrome"、"chrome_android"、"safari"、
"safari_beta"、"safari_ios"、"safari_ios_beta"、
"firefox"、"tor"
```

#### 会话管理（FetcherSession）

```python
from scrapling.fetchers import FetcherSession

with FetcherSession(
    impersonate='chrome',
    http3=True,
    stealthy_headers=True,
    timeout=30,
    retries=3
) as session:
    page1 = session.get('https://example.com/page1')
    page2 = session.post('https://example.com/api', json={'key': 'val'})
    page3 = session.get('https://example.com/page2')
    # 所有请求共享连接池，Cookie 自动持久化
```

Session 就像开了一个浏览器窗口，在这个窗口里的所有操作会保持登录状态。多个请求复用同一个连接，速度快很多（大约快10倍）。impersonate='chrome' 让服务器以为是真人在用 Chrome 访问，http3=True 启用最新协议提升速度。

**会话优势**：
- 比单次请求快约 **10 倍**（连接复用）
- Cookie 跨请求自动持久化
- 内存和 CPU 更高效
- 集中管理所有配置

#### 实用示例

```python
# 分页抓取
def scrape_all_pages():
    all_products = []
    with FetcherSession(impersonate='chrome') as session:
        page_num = 1
        while True:
            page = session.get(f'https://example.com/products?page={page_num}')
            products = page.css('.product')
            if not products:
                break
            for product in products:
                all_products.append({
                    'name': product.css('.name::text').get(),
                    'price': product.css('.price::text').get()
                })
            page_num += 1
    return all_products

# 下载文件
page = Fetcher.get('https://example.com/image.png')
with open('image.png', 'wb') as f:
    f.write(page.body)    # body 返回 bytes

# 带代理
page = Fetcher.get(
    'https://example.com',
    proxy='http://user:pass@proxy.server:8080'
)
```

几个常用场景。分页抓取是最常见的，用 while 循环翻页直到找不到内容；下载文件用 page.body 获取原始字节数据；proxy 参数用于需要代理的情况（比如防止被封 IP）。

> ⚠️ **注意**：`OPTIONS` 和 `HEAD` 方法暂不支持

### 5.3 DynamicFetcher（动态渲染）

基于 Playwright，支持完整的 JavaScript 渲染和浏览器自动化。

#### 三种运行模式

```python
from scrapling.fetchers import DynamicFetcher

# 1. 原生 Playwright（内置速度和隐身优化）
page = DynamicFetcher.fetch('https://example.com')

# 2. 真实 Chrome（更难被检测，需本地安装 Chrome）
# 先安装: playwright install chrome
page = DynamicFetcher.fetch('https://example.com', real_chrome=True)

# 3. CDP 远程连接（连接已运行的浏览器）
page = DynamicFetcher.fetch('https://example.com', cdp_url='ws://localhost:9222')
```

当网页需要 JavaScript 生成内容时用这个。它会启动一个真实的浏览器来加载页面，可以看到完整的渲染结果。real_chrome=True 用本机安装的 Chrome，伪装效果更好；CDP 模式可以连接自己调试好的浏览器环境。

#### 完整参数列表

| 参数 | 说明 |
|------|------|
| `url` | 目标 URL（必填）|
| `headless` | 无头模式（默认 `True`），`False` 显示浏览器界面 |
| `disable_resources` | 禁用图片/字体/媒体/样式等，提升约 25% 速度 |
| `cookies` | 设置 Cookie |
| `useragent` | 自定义 UA（否则自动生成真实 UA） |
| `network_idle` | 等待网络空闲 500ms 以上 |
| `load_dom` | 等待 DOM 内容加载完成（默认 `True`） |
| `timeout` | 超时毫秒数（默认 30000） |
| `wait` | 操作完成后额外等待毫秒数 |
| `page_action` | 导航后执行的自动化函数（接收 Playwright Page 对象） |
| `page_setup` | 导航前执行的设置函数（注册事件监听等） |
| `wait_selector` | 等待特定 CSS 选择器出现 |
| `wait_selector_state` | 等待状态：`attached`/`detached`/`visible`/`hidden` |
| `google_search` | 设置 Google 来源 referer（默认 `True`） |
| `extra_headers` | 额外请求头字典 |
| `proxy` | 代理（字符串或含 server/username/password 的字典） |
| `real_chrome` | 使用本地 Chrome 浏览器 |
| `locale` | 区域设置，如 `en-GB`、`zh-CN` |
| `timezone_id` | 浏览器时区 |
| `cdp_url` | CDP 连接 URL |
| `user_data_dir` | 用户数据目录（仅 Session 可用） |
| `blocked_domains` | 要拦截的域名集合（含子域名） |
| `block_ads` | 拦截约 3500 个广告/追踪域名 |
| `dns_over_https` | 通过 Cloudflare DoH 防止 DNS 泄漏 |
| `proxy_rotator` | ProxyRotator 实例 |
| `capture_xhr` | 正则 URL 模式，捕获匹配的 XHR/fetch 请求 |
| `extra_flags` | 额外浏览器启动参数列表 |

#### 代码示例

```python
# 资源控制（提速）
page = DynamicFetcher.fetch('https://example.com', disable_resources=True)

# 等待特定元素加载
page = DynamicFetcher.fetch(
    'https://spa-app.com',
    wait_selector='div.content',
    wait_selector_state='visible'
)

# 广告拦截
page = DynamicFetcher.fetch('https://example.com', block_ads=True)

# 域名拦截
page = DynamicFetcher.fetch(
    'https://example.com',
    blocked_domains={"ads.example.com", "tracker.net"}
)

# 浏览器自动化（滚动页面）
from playwright.sync_api import Page

def scroll_to_bottom(page: Page):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)

page = DynamicFetcher.fetch('https://example.com', page_action=scroll_to_bottom)

# 捕获 XHR/API 请求
from scrapling.fetchers import DynamicSession

with DynamicSession(
    capture_xhr=r"https://api\.example\.com/.*",
    headless=True
) as session:
    page = session.fetch('https://example.com')
    for xhr in page.captured_xhr:
        print(xhr.url, xhr.status)
        data = xhr.json()    # 如果是 JSON 响应
```

这些是常用技巧。disable_resources 禁用图片等资源提速；wait_selector 等特定内容出现再继续；block_ads 过滤广告；page_action 注入自定义脚本（比如滚动加载更多）；capture_xhr 捕获网页调用的 API 数据，有时直接拿 API 数据比解析 HTML 更方便。

#### 异步会话

```python
import asyncio
from scrapling.fetchers import AsyncDynamicSession

async def scrape_multiple():
    async with AsyncDynamicSession(
        network_idle=True,
        timeout=30000,
        max_pages=3    # 并发标签页池上限
    ) as session:
        pages = await asyncio.gather(
            session.fetch('https://spa-app1.com'),
            session.fetch('https://spa-app2.com'),
            session.fetch('https://dynamic-content.com')
        )
        return pages

asyncio.run(scrape_multiple())
```

需要同时抓多个页面时用这个。asyncio.gather 可以并发执行多个任务，max_pages 控制同时打开几个浏览器标签。network_idle=True 表示等网络不活跃了再抓数据，适合那些加载完还会发送请求的 SPA 应用。

### 5.4 StealthyFetcher（隐身绕过）

`StealthyFetcher` 是 `DynamicFetcher` 的高级版本，基于 Playwright + patchright，专为绕过反机器人系统设计。

#### 自动执行的隐身操作

| 操作 | 说明 |
|------|------|
| 🔒 CDP 运行时泄漏修复 | 阻止通过 CDP 检测 Playwright |
| 🔒 WebRTC 泄漏修复 | 防止真实 IP 泄漏（需启用 `block_webrtc=True`） |
| 🔒 JS 指纹隔离 | 移除大量 Playwright 标识符 |
| 🔒 Canvas 噪声 | 防止 Canvas 指纹识别（需启用 `hide_canvas=True`） |
| 🔒 无头模式检测修复 | 自动修补已知的无头模式检测方法 |

#### 基础使用

```python
from scrapling.fetchers import StealthyFetcher

# 同步
page = StealthyFetcher.fetch('https://example.com')

# 异步
page = await StealthyFetcher.async_fetch('https://example.com')
```

这是专门对付反爬虫的版本。它会模拟真实浏览器的各种特征（Canvas 指纹、WebRTC、鼠标轨迹等），让网站以为是真的人在访问。使用前要确保真的需要它，因为比普通版本慢很多。

#### 核心隐身参数（与 DynamicFetcher 的差异）

| 参数 | 说明 |
|------|------|
| `solve_cloudflare` | 自动解决所有类型 Cloudflare 验证（JS挑战/交互点击/隐形验证/嵌入式） |
| `block_webrtc` | 强制 WebRTC 遵守代理，防止本地 IP 泄漏 |
| `hide_canvas` | 为 Canvas 操作添加随机噪声，防止指纹识别 |
| `allow_webgl` | 默认开启（禁用 WebGL 会被大多数 WAF 检测到） |
| `init_script` | 页面创建时执行的 JS 文件路径 |

#### 完整实战示例

```python
# 绕过 Cloudflare 完整配置
page = StealthyFetcher.fetch(
    'https://cloudflare-protected-site.com',
    solve_cloudflare=True,
    block_webrtc=True,
    real_chrome=True,          # 使用真实 Chrome
    hide_canvas=True,
    google_search=True,
    proxy='http://user:pass@proxy:8080',
    timeout=60000,             # ⚠️ 使用 Cloudflare 解析器至少需要 60 秒
    headless=True
)

# 等待 Cloudflare 验证后的内容加载
page = StealthyFetcher.fetch(
    'https://protected.com',
    solve_cloudflare=True,
    wait_selector='div.main-content',
    wait_selector_state='visible',
    timeout=90000
)

# 抓取 Amazon 商品
def scrape_amazon(url):
    page = StealthyFetcher.fetch(url)
    return {
        'title': page.css('#productTitle::text').get().clean(),
        'price': page.css('.a-price .a-offscreen::text').get(),
        'rating': page.css('.a-popover-trigger .a-color-base::text').get(),
        'reviews': page.css('#acrCustomerReviewText::text').re_first(r'[\d,]+'),
        'features': page.css('#feature-bullets li span::text').getall(),
    }
```

这是 StealthyFetcher 的完整配置示例。solve_cloudflare 自动通过验证，block_webrtc 防止真实 IP 泄露，hide_canvas 给 Canvas 加上随机噪声。timeout 必须设长一点，因为需要等待验证完成。示例里的 Amazon 爬虫展示了实际应用中如何提取商品信息。

#### 会话管理（StealthySession）

```python
from scrapling.fetchers import StealthySession, AsyncStealthySession

# 同步会话
with StealthySession(
    headless=True,
    real_chrome=True,
    block_webrtc=True,
    solve_cloudflare=True
) as session:
    page1 = session.fetch('https://site1.com')
    page2 = session.fetch('https://site2.com')
    # 复用同一浏览器的标签页

# 异步会话（带标签页池）
async with AsyncStealthySession(
    real_chrome=True,
    block_webrtc=True,
    solve_cloudflare=True,
    timeout=60000,
    max_pages=3    # 最大并发标签页
) as session:
    pages = await asyncio.gather(
        session.fetch('https://protected1.com'),
        session.fetch('https://protected2.com'),
        session.fetch('https://protected3.com')
    )
```

批量抓取被保护的网站时用这个。同步版本适合一个个抓，异步版本可以同时开多个标签页并行抓取（max_pages 控制最多几个）。会话复用同一个浏览器实例，省去重复初始化的时间。

> ⚠️ **注意**：v0.3.13 后，`stealth`/`hide_canvas`/`disable_webgl` 等选项已从 `DynamicFetcher` 移至 `StealthyFetcher`

### 5.5 代理轮换

```python
from scrapling.fetchers import ProxyRotator, FetcherSession

# 创建轮换器（循环策略）
rotator = ProxyRotator([
    'http://proxy1:8080',
    'http://proxy2:8080',
    'http://user:pass@proxy3:8080',
])

# 随机策略
rotator_random = ProxyRotator(
    ['http://p1:8080', 'http://p2:8080'],
    strategy='random'
)

# 在 Session 中使用
with FetcherSession(proxy_rotator=rotator, impersonate='chrome') as session:
    page1 = session.get('https://example.com/page1')
    page2 = session.get('https://example.com/page2')
    print(page1.meta['proxy'])    # 查看本次使用的代理
```

爬取大量数据时需要轮换 IP 防止被封。用 ProxyRotator 管理多个代理，它会自动切换。可以选循环策略（按顺序用完再从头开始）或随机策略。meta['proxy'] 可以看到当前用的是哪个代理，方便排查问题。

### 5.6 异步使用

```python
import asyncio
from scrapling.fetchers import AsyncFetcher, AsyncStealthySession

# AsyncFetcher（静态请求）
async def main():
    page = await AsyncFetcher.get('https://example.com')
    data = page.css('.content::text').getall()
    return data

# 并发请求
async def concurrent_scrape():
    async with AsyncStealthySession(max_pages=5) as session:
        urls = [f'https://example.com/page{i}' for i in range(1, 6)]
        tasks = [session.fetch(url) for url in urls]
        
        # 查看标签页池状态
        print("池状态:", session.get_pool_stats())
        
        results = await asyncio.gather(*tasks)
        return results

asyncio.run(concurrent_scrape())
```

如果你的程序已经用了 asyncio，直接用 AsyncFetcher 更自然。AsyncFetcher.get() 是异步的 await 调用，asyncio.gather() 同时发起多个请求。get_pool_stats() 查看当前标签页的使用情况，方便监控爬虫状态。

---

## 6. 爬虫框架（Spiders）

Spider 框架是 Scrapling 的高级功能，提供 Scrapy 风格的 API 用于构建复杂爬虫。

### 6.1 第一个爬虫

```python
from scrapling.spiders import Spider, Response

class QuotesSpider(Spider):
    name = "quotes"                              # 爬虫唯一标识
    start_urls = ["https://quotes.toscrape.com"] # 起始 URL 列表
    
    async def parse(self, response: Response):   # ⚠️ 必须是异步生成器
        for quote in response.css("div.quote"):
            yield {    # yield 字典即为抓取的数据
                "text": quote.css("span.text::text").get(""),
                "author": quote.css("small.author::text").get(""),
            }

# 运行爬虫
result = QuotesSpider().start()

# 访问结果
for item in result.items:
    print(item["text"], "-", item["author"])

# 查看统计
print(f"共 {result.stats.items_scraped} 条")
print(f"耗时 {result.stats.elapsed_seconds:.1f} 秒")
```

这是 Scrapling 爬虫框架的最小示例。定义一个继承 Spider 的类，设置 name（爬虫名字）和 start_urls（从哪些页面开始），然后写一个 parse 方法处理每个页面返回的数据。yield 的字典就是抓到的数据，框架会自动收集起来。result.items 是所有数据，result.stats 是统计信息。

**爬虫三要素**：

| 要素 | 说明 |
|------|------|
| `name` | 爬虫的唯一标识符 |
| `start_urls` | 起始 URL 列表（列表形式） |
| `parse()` | **异步生成器**，处理响应并 `yield` 数据或下一个请求 |

### 6.2 跟进链接与多回调

```python
class QuotesSpider(Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com"]
    allowed_domains = {"quotes.toscrape.com"}   # 限制只爬这个域名（含子域名）
    robots_txt_obey = True                       # 遵守 robots.txt

    async def parse(self, response: Response):
        for quote in response.css("div.quote"):
            yield {"text": quote.css("span.text::text").get("")}
        
        # 跟进下一页（自动处理相对 URL）
        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

        # 进入详情页（使用不同回调）
        for link in response.css("a.product::attr(href)").getall():
            yield response.follow(link, callback=self.parse_detail)

    async def parse_detail(self, response: Response):
        yield {
            "title": response.css("h1::text").get(""),
            "price": response.css(".price::text").get(""),
        }
```

爬虫不仅要抓首页，还要自动访问其他页面。response.follow() 会自动把相对链接转成完整链接。callback 指定用哪个方法处理新页面，比如列表页用 parse，详情页用 parse_detail。allowed_domains 防止爬到外链去，robots_txt_obey 是礼貌爬虫的标配。

> ⚠️ **规则**：所有回调方法必须是 `async def` + `yield` 的异步生成器

#### 导出数据

```python
result = QuotesSpider().start()

result.items.to_json("quotes.json")            # JSON 格式
result.items.to_json("quotes.json", indent=True)  # 格式化 JSON
result.items.to_jsonl("quotes.jsonl")          # JSON Lines 格式
# 目录不存在会自动创建
```

抓取的数据默认保存在内存里，需要导出到文件。to_json 输出标准 JSON 格式（带 indent 更美观），to_jsonl 每行一条 JSON 数据，更适合处理大数据量。目录不存在会自动创建。

### 6.3 会话管理（Sessions）

在 Spider 中可以混合使用不同类型的获取器（HTTP、浏览器、隐身浏览器）。

> ⚠️ **重要**：Spider 内必须使用会话的 **Async 版本**（如 `AsyncStealthySession`）

```python
from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import FetcherSession, AsyncStealthySession

class MultiSessionSpider(Spider):
    name = "multi"
    start_urls = ["https://shop.example.com/products"]

    def configure_sessions(self, manager):
        # 添加快速 HTTP 会话（自动成为默认）
        manager.add("http", FetcherSession(impersonate="chrome"))
        
        # 添加隐身浏览器会话（lazy=True 表示首次使用时才启动）
        manager.add(
            "stealth",
            AsyncStealthySession(headless=True, network_idle=True),
            lazy=True
        )

    async def parse(self, response: Response):
        for link in response.css("a.product::attr(href)").getall():
            # 按 sid 路由到不同会话
            yield response.follow(link, sid="stealth", callback=self.parse_product)

        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            # 不指定 sid 时使用默认会话（http）
            yield response.follow(next_page)

    async def parse_product(self, response: Response):
        yield {
            "name": response.css("h1::text").get(""),
            "price": response.css(".price::text").get(""),
        }
```

大型爬虫可以同时使用多种"武器"。比如列表页用快速的 HTTP 请求就够了，详情页需要 JavaScript 渲染就用隐身浏览器。通过 configure_sessions 注册多个会话，然后用 sid 参数决定每个请求走哪个通道。lazy=True 让浏览器会话只在用到时才启动，省资源。

#### `manager.add()` 参数

| 参数 | 说明 |
|------|------|
| `session_id` | 会话唯一标识（字符串） |
| `session` | 会话实例 |
| `default=False` | 是否设为默认会话 |
| `lazy=False` | 延迟启动（适合浏览器会话） |

#### 在请求中传递会话参数

```python
async def parse(self, response: Response):
    # 按请求传递额外参数
    yield Request(
        "https://api.example.com/data",
        headers={"Authorization": "Bearer token"},
        callback=self.parse_api,
    )
    
    # POST 请求
    yield Request(
        "https://example.com/submit",
        method="POST",
        data={"field": "value"},
        sid="http",
        callback=self.parse_result,
    )
    
    # 浏览器会话参数
    yield Request(
        "https://protected.com",
        sid="stealth",
        solve_cloudflare=True,
        block_webrtc=True,
        network_idle=True,
        callback=self.parse_protected,
    )
```

Request 对象比 response.follow() 更底层，但功能更全面。可以直接指定 HTTP 方法、请求头、POST 数据等。对于特殊请求（比如调用需要 token 的 API），用 Request 更灵活。sid 参数指定走哪个会话通道。

### 6.4 代理与域名过滤

```python
class PoliteSpider(Spider):
    name = "polite"
    start_urls = ["https://example.com"]
    allowed_domains = {"example.com"}    # 自动匹配子域名
    robots_txt_obey = True               # 遵守 robots.txt

    def configure_sessions(self, manager):
        from scrapling.fetchers import ProxyRotator
        rotator = ProxyRotator([
            'http://proxy1:8080',
            'http://proxy2:8080',
        ])
        manager.add("default", FetcherSession(proxy_rotator=rotator))

    async def parse(self, response: Response):
        ...
```

这个爬虫懂得"礼貌"。allowed_domains 只让它在指定域名内爬，不会跑到外链去。robots_txt_obey 会读取网站的 robots.txt 文件，按规矩办事。配合代理轮换，爬取量大时不容易被封。

### 6.5 高级特性

#### 并发控制

```python
class FastSpider(Spider):
    name = "fast"
    start_urls = ["https://example.com"]
    concurrent_requests = 16              # 最大并发请求数（默认 4）
    concurrent_requests_per_domain = 4   # 每域名最大并发（默认 0，不限制）
    download_delay = 0.5                  # 请求间隔秒数（默认 0）
    robots_txt_obey = False              # robots.txt 遵守（默认 False）
```

调整爬虫的"力度"。concurrent_requests 控制同时发几个请求，太快可能被封；concurrent_requests_per_domain 限制每个站点的并发，防止对单个网站压力太大；download_delay 在请求之间加间隔，更温和一些。

#### 暂停与恢复

```python
# 首次运行（指定 crawldir 启用检查点）
result = QuotesSpider(crawldir="./crawl_data").start()

# 按 Ctrl+C → 等待进行中的请求完成 → 保存检查点 → 退出
# 再次 Ctrl+C → 立即强制退出

# 下次运行（自动从断点恢复，跳过已爬取的 URL）
result = QuotesSpider(crawldir="./crawl_data").start()

# 自定义检查点保存间隔（秒）
result = QuotesSpider(crawldir="./crawl_data", interval=120.0).start()
```

爬取大量数据时可能需要中途停止。指定 crawldir 后，框架会保存"爬到哪里了"的检查点。Ctrl+C 一次是优雅退出（等当前请求完成），按两次是强制退出。下次运行会自动从断点继续，不会重复抓取。

#### 开发模式（缓存响应）

```python
class DebugSpider(Spider):
    name = "debug"
    start_urls = ["https://example.com"]
    development_mode = True          # 启用开发模式
    development_cache_dir = "./cache"  # 自定义缓存目录（默认 .scrapling_cache/）
    
    async def parse(self, response: Response):
        # 首次运行：实际发请求 + 缓存到磁盘
        # 后续运行：直接从磁盘读取（完全跳过网络！）
        yield {"title": response.css("title::text").get()}
```

调试爬虫时频繁发请求很烦人。开启开发模式后，第一次会真正请求网络并缓存结果，之后每次运行都从本地读取，秒开。而且不用担心重复请求浪费资源或被封，适合调试解析逻辑。

> ⚠️ **警告**：切勿在生产环境启用开发模式！

#### 流式处理

```python
import asyncio
from scrapling.spiders import Spider, Response

class StreamSpider(Spider):
    name = "stream"
    start_urls = ["https://quotes.toscrape.com"]

    async def parse(self, response: Response):
        for quote in response.css("div.quote"):
            yield {"text": quote.css("span.text::text").get("")}

async def main():
    spider = StreamSpider()
    async for item in spider.stream():
        print(item)    # 实时获取每个数据
        print("当前统计:", spider.stats.items_scraped)

asyncio.run(main())

# 支持与暂停结合
async def main_with_pause():
    spider = StreamSpider(crawldir="./data")
    async for item in spider.stream():
        process(item)
        if should_stop():
            await spider.pause()    # 代码触发暂停
            break
```

不用等爬虫全部跑完，用 stream() 可以实时拿到每条数据。配合 async for 循环，每抓到一条就处理一条，适合边爬边写入数据库或实时分析。还可以和暂停功能结合，满足条件就停止。

#### 生命周期钩子

```python
class HookedSpider(Spider):
    name = "hooked"
    start_urls = ["https://example.com"]

    def on_start(self, resuming: bool = False):
        """爬取开始前（用于初始化）"""
        if resuming:
            print("从断点继续...")
        else:
            print("开始新的爬取...")
        self.db = setup_database()

    def on_close(self):
        """爬取结束后（用于清理）"""
        self.db.close()
        print("爬取结束，资源已清理")

    def on_error(self, request, error: Exception):
        """请求失败时"""
        print(f"请求失败: {request.url} - {error}")
        self.logger.error(f"Error on {request.url}: {error}")

    def on_scraped_item(self, item: dict):
        """每个数据项被抓取后"""
        # 返回修改后的 item → 保留
        # 返回 None → 丢弃这条数据
        if item.get('price', 0) > 0:
            return item    # 只保留有价格的数据
        return None        # 丢弃没有价格的数据

    def start_requests(self):
        """自定义起始请求（代替 start_urls）"""
        # 示例：先登录再爬取
        from scrapling.spiders import Request
        yield Request(
            'https://example.com/login',
            method='POST',
            data={'username': 'user', 'password': 'pass'},
            callback=self.after_login
        )

    async def after_login(self, response: Response):
        yield response.follow('/protected-page', callback=self.parse)

    async def parse(self, response: Response):
        yield {"data": response.css('.content::text').get()}
```

钩子是框架在不同阶段调用的函数。on_start 初始化数据库连接，on_close 做清理工作，on_error 记录失败请求，on_scraped_item 可以过滤或修改数据。start_requests 可以代替 start_urls，实现"先登录再爬取"的流程。

#### 日志配置

```python
class LoggedSpider(Spider):
    name = "logged"
    start_urls = ["https://example.com"]
    logging_level = "INFO"                      # 日志级别
    logging_format = "%(asctime)s - %(message)s" # 格式
    logging_date_format = "%Y-%m-%d %H:%M:%S"   # 日期格式
    log_file = "./logs/spider.log"              # 日志文件（自动创建目录）

    async def parse(self, response: Response):
        self.logger.info(f"正在解析: {response.url}")
        self.logger.debug("详细调试信息")
        yield {"title": response.css("title::text").get()}
```

爬虫运行时需要记录日志。logging_level 控制显示多少信息（DEBUG 最详细，ERROR 只显示错误），log_file 指定日志保存路径。self.logger 可以在代码里自定义输出内容，方便排查问题。

#### 使用 uvloop 加速

```bash
pip install uvloop      # Linux/Mac
pip install winloop     # Windows
```

```python
result = QuotesSpider().start(use_uvloop=True)   # I/O 密集型爬取可提升吞吐量
```

uvloop 是一个比标准 asyncio 更快的事件循环。爬取大量页面时，开启它可以获得显著的性能提升。Linux/Mac 用 uvloop，Windows 用 winloop，安装对应的包后加一行参数即可。

### 6.6 结果与统计

```python
result = QuotesSpider().start()

# 基础状态
print(result.completed)    # 是否完成
print(result.paused)       # 是否暂停

# 访问数据
for item in result.items:
    print(item)

# 统计信息
stats = result.stats
print(f"总请求数: {stats.requests_count}")
print(f"失败请求: {stats.failed_requests_count}")
print(f"被阻请求: {stats.blocked_requests_count}")
print(f"robots 拒绝: {stats.robots_disallowed_count}")
print(f"站外过滤: {stats.offsite_requests_count}")
print(f"抓取数据: {stats.items_scraped}")
print(f"丢弃数据: {stats.items_dropped}")
print(f"响应字节: {stats.bytes_received}")
print(f"耗时（秒）: {stats.elapsed_seconds}")
print(f"每秒请求: {stats.requests_per_second}")
print(f"状态码分布: {stats.response_status_count}")

# 导出统计
stats_dict = stats.to_dict()
```

爬虫跑完后可以查看各种统计。result.completed 判断是否正常结束，result.paused 判断是否被暂停。stats 里记录了请求数、失败数、数据条数、耗时等详细信息，可以用来评估爬虫效率和排查问题。

---

## 7. 命令行工具（CLI）

安装 CLI 功能：
```bash
pip install "scrapling[shell]"
```

### 交互式 Shell

```bash
scrapling shell
```

在 Shell 中可以直接操作响应对象，适合快速测试选择器：

```python
# Shell 内部使用示例
page = fetch('https://quotes.toscrape.com')
page.css('.quote .text::text').getall()
page.find_by_text('Albert Einstein', partial=True)
```

不想写代码又想知道选择器对不对？用这个交互式 Shell。它像 Python 解释器一样，输入命令立即看到结果。fetch() 是内置函数直接获取页面，然后可以随意试验各种选择器，直到找到正确的。

### extract 命令

#### 基本用法

```bash
# GET 请求并保存内容
scrapling extract get 'https://example.com' output.md
scrapling extract get 'https://example.com' output.txt
scrapling extract get 'https://example.com' output.html

# 动态渲染（使用浏览器）
scrapling extract fetch 'https://spa-app.com' output.html

# 隐身模式（绕过反爬）
scrapling extract stealthy-fetch 'https://protected.com' output.html
```

不需要写 Python 代码，直接在命令行抓网页。get 是普通请求，fetch 用浏览器渲染，stealthy-fetch 用于有反爬的网站。输出的文件格式由扩展名决定（.md/.txt/.html）。

#### 常用选项

```bash
# 指定 CSS 选择器（只提取匹配的内容）
scrapling extract get 'https://example.com' output.md \
    --css-selector '#main-content'

# 模拟特定浏览器
scrapling extract get 'https://example.com' output.md \
    --impersonate 'chrome'

# 显示浏览器窗口（非无头模式）
scrapling extract fetch 'https://example.com' output.md \
    --no-headless

# 绕过 Cloudflare
scrapling extract stealthy-fetch 'https://nopecha.com/demo/cloudflare' output.html \
    --css-selector '#padded_content a' \
    --solve-cloudflare
```

这些选项让命令行更灵活。--css-selector 只保存匹配的内容（比如只取正文部分），--impersonate 伪装成特定浏览器，--no-headless 打开浏览器窗口可以观察行为，--solve-cloudflare 自动通过验证。

#### CLI 参数表

| 参数 | 说明 |
|------|------|
| `--css-selector` | 只提取匹配 CSS 选择器的内容 |
| `--impersonate` | 浏览器 TLS 指纹（`chrome`/`firefox135` 等） |
| `--no-headless` | 显示浏览器窗口 |
| `--solve-cloudflare` | 自动解决 Cloudflare 验证 |

---

## 8. AI 集成（MCP Server）

Scrapling 内置 MCP（Model Context Protocol）服务器，可与 Claude、Cursor 等 AI 工具集成。

### 安装

```bash
pip install "scrapling[ai]"
```

### 核心用途

- 在将网页内容传给 AI 之前，先用 Scrapling **提取目标内容**
- 减少传给 AI 的 token 数量，降低成本
- 支持 Cloudflare 绕过，AI 可抓取受保护网页

### 配置（Claude Desktop 示例）

```json
{
  "mcpServers": {
    "scrapling": {
      "command": "scrapling",
      "args": ["mcp"]
    }
  }
}
```

让 AI 助手直接帮你抓网页。把 Scrapling 配置成 MCP 服务器后，Claude 等 AI 工具就能用它抓取网页内容、智能提取信息，甚至绕过反爬。适合需要 AI 分析网页但网页本身难以访问的场景。

---

## 9. 性能基准测试

### 文本提取速度（5000 个嵌套元素）

| 排名 | 库 | 时间 (ms) | 相对 Scrapling |
|------|------|-----------|----------------|
| 🥇 1 | **Scrapling** | **2.02** | **1.0x** |
| 🥈 2 | Parsel/Scrapy | 2.04 | 1.01x |
| 🥉 3 | Raw Lxml | 2.54 | 1.26x |
| 4 | PyQuery | 24.17 | ~12x |
| 5 | Selectolax | 82.63 | ~41x |
| 6 | BS4 + Lxml | 1584.31 | ~784x |
| 7 | BS4 + html5lib | 3391.91 | ~1679x |

### 相似度查找性能

| 库 | 时间 (ms) | 相对 Scrapling |
|------|-----------|----------------|
| **Scrapling** | **2.39** | **1.0x** |
| AutoScraper | 12.45 | ~5.2x |

### JSON 序列化

- 比 Python 标准库快约 **10 倍**

### 其他指标

| 指标 | 数值 |
|------|------|
| 测试覆盖率 | 92% |
| 类型提示覆盖 | 100% |
| GitHub Stars | 36.8k+ |

---

## 10. 实战综合案例

### 案例一：简单爬取（静态页面）

```python
from scrapling.fetchers import Fetcher

def scrape_books():
    """爬取书店网站所有图书"""
    all_books = []
    page_num = 1
    
    with Fetcher() as session:
        while True:
            url = f'https://books.toscrape.com/catalogue/page-{page_num}.html'
            page = session.get(url, impersonate='chrome')
            
            books = page.css('.product_pod')
            if not books:
                break
            
            for book in books:
                all_books.append({
                    'title': book.css('h3 a::attr(title)').get(''),
                    'price': book.css('.price_color::text').get(''),
                    'rating': book.css('p.star-rating::attr(class)').re_first(r'star-rating (\w+)'),
                    'in_stock': bool(book.css('.instock.availability')),
                })
            page_num += 1
    
    return all_books
```

这是最基础的爬虫模式。while 循环翻页，每页抓完检查有没有内容，没有就退出。FetcherSession 保持连接复用。用 re_first 从 class 属性里提取星级（如 "star-rating Four" 提取出 "Four"）。

### 案例二：Spider 爬取（多页分页）

```python
from scrapling.spiders import Spider, Response

class BookSpider(Spider):
    """Scrapy 风格的图书爬虫"""
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    allowed_domains = {"books.toscrape.com"}
    concurrent_requests = 8
    download_delay = 0.3

    async def parse(self, response: Response):
        for book in response.css('.product_pod'):
            yield {
                'title': book.css('h3 a::attr(title)').get(''),
                'price': book.css('.price_color::text').get(''),
            }
        
        next_page = response.css('.next a::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

if __name__ == '__main__':
    result = BookSpider(crawldir='./book_crawl').start()
    print(f"共抓取 {result.stats.items_scraped} 本图书")
    result.items.to_json('books.json', indent=True)
```

用 Spider 框架重写，实现自动翻页。concurrent_requests=8 同时处理 8 个请求，download_delay=0.3 每页间隔 0.3 秒。找到"下一页"链接就 yield 回去，框架会自动跟进。crawldir 启用断点续传功能。

### 案例三：绕过反爬（隐身模式）

```python
from scrapling.fetchers import StealthyFetcher, AsyncStealthySession  # 导入隐身抓取器和异步会话
import asyncio  # 导入异步支持

def scrape_protected_site(url):
    """绕过 Cloudflare 的完整配置"""  # 函数文档说明用途
    page = StealthyFetcher.fetch(  # 调用隐身浏览器获取页面
        url,  # 目标网址
        solve_cloudflare=True,  # 自动解决 Cloudflare 验证
        block_webrtc=True,  # 阻止 WebRTC 泄露真实 IP
        hide_canvas=True,  # 给 Canvas 指纹添加随机噪声
        real_chrome=True,  # 使用真实 Chrome 而非 Playwright 模拟
        headless=True,  # 无头模式（不显示浏览器窗口）
        google_search=True,  # 伪装搜索来源
        timeout=90000,  # 超时时间 90 秒（Cloudflare 需要更长等待）
        wait_selector='div.main-content',  # 等待主内容区域出现
        wait_selector_state='visible'  # 等待元素可见
    )
    return page  # 返回解析后的页面对象

async def batch_scrape(urls):
    """批量异步隐身抓取"""  # 函数文档说明用途
    async with AsyncStealthySession(  # 创建异步隐身会话
        headless=True,  # 无头模式
        solve_cloudflare=True,  # 自动通过 Cloudflare
        block_webrtc=True,  # 阻止 IP 泄露
        timeout=60000,  # 超时 60 秒
        max_pages=3  # 最多同时打开 3 个标签页
    ) as session:  # session 是会话实例
        tasks = [session.fetch(url) for url in urls]  # 为每个 URL 创建抓取任务
        pages = await asyncio.gather(*tasks, return_exceptions=True)  # 并发执行，失败返回异常而非中断
        
        results = []  # 初始化结果列表
        for i, page in enumerate(pages):  # 遍历抓取结果
            if isinstance(page, Exception):  # 如果是异常（抓取失败）
                print(f"URL {urls[i]} 失败: {page}")  # 打印错误信息
            else:  # 如果是正常页面
                results.append({  # 添加到结果列表
                    'url': urls[i],  # 记录原始 URL
                    'title': page.css('title::text').get(''),  # 提取页面标题
                    'content': page.css('main::text').getall(),  # 提取主内容区域所有文本
                })
        return results  # 返回所有成功抓取的结果
```

对付有 Cloudflare 保护的网站。solve_cloudflare 自动通过验证，block_webrtc 防止 IP 泄露，hide_canvas 防止指纹识别。batch_scrape 用 asyncio.gather 并发抓取多个 URL，return_exceptions=True 保证一个失败不影响其他。

### 案例四：自适应抓取（应对网站改版）

```python
from scrapling.fetchers import Fetcher

def build_adaptive_scraper():
    """
    构建一个能应对网站改版的抓取器
    第一次运行：保存元素结构
    后续运行：即使网站改版也能找到正确元素
    """
    Fetcher.configure(adaptive=True, adaptive_domain='shop.example.com')
    
    # 第一次运行（建立"记忆"）
    page = Fetcher.get('https://shop.example.com/products')
    products = page.css('.product-card', auto_save=True)
    
    for p in products:
        print(p.css('.product-name::text').get())

def run_after_website_update():
    """网站改版后，仍能定位正确的元素"""
    Fetcher.configure(adaptive=True, adaptive_domain='shop.example.com')
    
    page = Fetcher.get('https://shop.example.com/products')
    # 即使 CSS 类名变了，也能找到"产品卡片"元素
    products = page.css('.new-product-card', adaptive=True)
    
    for p in products:
        print(p.css('::text').get())
```

自适应抓取的完整演示。第一次用 auto_save 保存元素"记忆"，网站改版后用 adaptive 自动匹配。adaptive_domain 让不同 URL 共享同一份数据。这个功能对长期运行的监控任务特别有用。

### 案例五：多会话复杂爬虫

```python
from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import FetcherSession, AsyncStealthySession

class EcommerceSpider(Spider):
    """电商爬虫：结合 HTTP 和隐身浏览器"""
    name = "ecommerce"
    start_urls = ["https://shop.example.com/categories"]
    concurrent_requests = 10
    download_delay = 0.5

    def configure_sessions(self, manager):
        # 快速 HTTP 会话（用于分类/列表页）
        manager.add("fast", FetcherSession(
            impersonate="chrome",
            stealthy_headers=True
        ))
        # 隐身浏览器会话（用于详情页，懒加载启动）
        manager.add("stealth", AsyncStealthySession(
            headless=True,
            network_idle=True,
            capture_xhr=r"https://api\.shop\.example\.com/.*"
        ), lazy=True)

    def on_start(self, resuming: bool = False):
        self.product_count = 0
        self.logger.info(f"{'继续' if resuming else '开始'}爬取")

    def on_scraped_item(self, item: dict):
        """过滤：只保留有库存的商品"""
        if item.get('in_stock'):
            self.product_count += 1
            return item
        return None

    def on_error(self, request, error):
        self.logger.warning(f"请求失败: {request.url}")

    def on_close(self):
        self.logger.info(f"爬取完成，有效商品: {self.product_count}")

    async def parse(self, response: Response):
        """解析分类列表"""
        for category in response.css('.category-link::attr(href)').getall():
            yield response.follow(category, callback=self.parse_category)

    async def parse_category(self, response: Response):
        """解析商品列表"""
        for product_link in response.css('.product-link::attr(href)').getall():
            yield Request(
                product_link,
                sid="stealth",
                callback=self.parse_product,
                network_idle=True
            )
        
        next_page = response.css('.pagination .next::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_category)

    async def parse_product(self, response: Response):
        """解析商品详情"""
        # 捕获 API 数据
        for xhr in response.captured_xhr:
            if 'inventory' in xhr.url:
                stock_data = xhr.json()
                break
        else:
            stock_data = {}

        yield {
            "name": response.css("h1.product-title::text").get("").clean(),
            "price": response.css(".price::text").re_first(r"[\d\.]+"),
            "description": response.css(".description::text").getall(),
            "in_stock": stock_data.get('available', False),
            "images": response.css(".product-image::attr(src)").getall(),
            "url": response.url,
        }


if __name__ == "__main__":
    result = EcommerceSpider(crawldir="./ecommerce_crawl").start()
    
    print(f"✅ 爬取完成！")
    print(f"📊 有效商品: {result.stats.items_scraped}")
    print(f"⏱️ 耗时: {result.stats.elapsed_seconds:.1f} 秒")
    print(f"🌐 总请求: {result.stats.requests_count}")
    
    result.items.to_json("products.json", indent=True)
    result.items.to_jsonl("products.jsonl")
```

这是一个生产级别的完整爬虫示例。列表页用快速 HTTP，详情页用隐身浏览器（需要 JavaScript）。capture_xhr 捕获商品详情页调用的库存 API，直接拿 JSON 数据比解析 HTML 更可靠。on_scraped_item 过滤掉无库存商品。

---

## 11. 常见问题与最佳实践

### Q1：如何选择合适的 Fetcher？

```
页面是否需要执行 JavaScript？
  ├── 否 → Fetcher（最快）
  └── 是 → 是否有反爬检测？
             ├── 否 → DynamicFetcher
             └── 是 → StealthyFetcher
                      ├── 有 Cloudflare？→ 设置 solve_cloudflare=True
                      └── 其他？→ 尝试 block_webrtc=True + hide_canvas=True
```

### Q2：StealthyFetcher 绕过 Cloudflare 失败怎么办？

1. 确保 `timeout` 至少设为 `60000`（60秒）
2. 使用 `real_chrome=True`（真实 Chrome 更难被检测）
3. 配合 `wait_selector` 确保内容加载完成
4. 尝试使用真实 IP 代理（`proxy` 参数）
5. 开启 `headless=False` 观察浏览器行为

### Q3：自适应抓取匹配到错误元素？

```python
# 使用更精确的选择器
products = page.css('.product-list > .product-card', auto_save=True)

# 通过文本内容定位更精准的上下文
product_title = page.find_by_text('Product Name')
product_card = product_title.parent.parent    # 向上两级到卡片
page.save(product_card, 'product_card')

# 检查已保存的数据
saved = page.retrieve('product_card')
print(saved)
```

如果自适应匹配不准确，可以手动干预。用 find_by_text 找到关键元素后，用 .parent 往上走两级到卡片容器，然后手动保存。retrieve 可以查看保存的信息是否正确。

### Q4：Spider 爬取速度慢？

```python
class FastSpider(Spider):
    name = "fast"
    concurrent_requests = 32           # 提高并发数
    download_delay = 0                  # 去掉延迟
    
    def configure_sessions(self, manager):
        manager.add("default", FetcherSession(
            impersonate='chrome',
            http3=True                   # 启用 HTTP/3
        ))

# 启用 uvloop
result = FastSpider().start(use_uvloop=True)
```

提速的几个方法：提高并发数（但别太高会封 IP），关闭延迟，启用 HTTP/3 协议，安装 uvloop 加速事件循环。一般并发 16-32 比较安全，具体看目标网站的承受能力。

### Q5：如何处理登录态网站？

```python
from scrapling.fetchers import FetcherSession

with FetcherSession(impersonate='chrome') as session:
    # 1. 登录
    login_page = session.post(
        'https://example.com/login',
        data={'username': 'user', 'password': 'pass'},
        stealthy_headers=True
    )
    
    # 2. 检查是否成功（Cookie 自动保存在 session 中）
    if login_page.css('.logged-in'):
        # 3. 访问受保护页面
        page = session.get('https://example.com/protected')
        data = page.css('.content::text').getall()
```

登录态抓取的关键是保持 Cookie。FetcherSession 会自动保存登录后的 Cookie，后续请求会自动带上。所以先用 post 登录，成功后直接 get 受保护的页面就行，不需要再传 cookie 参数。

### 最佳实践总结

| 场景 | 推荐方案 |
|------|----------|
| 快速抓取 API | `Fetcher.get()` + `impersonate='chrome'` |
| 批量抓取多个 URL | `FetcherSession` + 连接复用 |
| SPA/动态网页 | `DynamicFetcher` + `network_idle=True` |
| Cloudflare 防护 | `StealthyFetcher` + `solve_cloudflare=True` + `timeout=60000` |
| 大规模爬取 | `Spider` + `concurrent_requests` 调优 |
| 需要暂停/恢复 | `Spider(crawldir='...')` |
| 实时数据处理 | `spider.stream()` |
| 应对网站改版 | `auto_save=True` + `adaptive=True` |
| 调试解析逻辑 | `development_mode=True` |

---

## 参考资源

- 📖 **官方文档**：https://scrapling.readthedocs.io/en/latest/
- 💻 **GitHub**：https://github.com/D4Vinci/Scrapling
- 📦 **PyPI**：https://pypi.org/project/scrapling/
- 🐳 **Docker**：`docker pull pyd4vinci/scrapling`
- 🤖 **MCP 技能**：https://www.modelscope.cn/skills/@d4vinci/Scrapling-Skill

> 本笔记基于 Scrapling v0.4.6 官方文档整理，涵盖从基础到高级的完整使用指南。如有更新，请参考官方文档。

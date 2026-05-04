# 🎨 Residency Tracker

自动爬虫,每天检查艺术驻留网站,把所有 open call 整理成一个可筛选的网页。

**给 Weijia 用 — 议题:女性、移民、酷儿、离散、代际、科技。**

---

## 📋 它能做什么

- ✅ 每天自动爬 20+ 个艺术驻留网站(可自己加)
- ✅ 自动抽取 deadline,按截止日排序
- ✅ 自动识别"主题契合度"(看内容里有没有 women / migration / queer 等关键词)
- ✅ 标记"新发现 vs 已经见过的"
- ✅ 紧急的(7 天内截止)会被高亮
- ✅ 生成一个网页,可以按机构、tag、时间筛选
- ✅ 完全免费(GitHub Actions + GitHub Pages)

---

## 🚀 第一次安装(20-30 分钟)

### 第 1 步:在 GitHub 上创建 repo

1. 登录 https://github.com
2. 点右上角 **+** → **New repository**
3. Repository name 填 `residency-tracker`
4. **Public**(必须公开,GitHub Pages 免费版需要)
5. ✅ 勾选 **Add a README file**(随便加点东西就行)
6. 点 **Create repository**

### 第 2 步:把这些文件上传到 repo

**最简单的办法:浏览器拖拽**

1. 在你的 repo 主页,点 **Add file** → **Upload files**
2. 把本项目里的所有文件 / 文件夹**拖进**网页(包括 `.github` 文件夹 — 这是关键!)
3. 在底部 commit message 写 "initial setup"
4. 点 **Commit changes**

> ⚠️ 如果拖拽 `.github` 文件夹失败,改用 GitHub Desktop:
> 1. 下载 https://desktop.github.com/
> 2. 登录后 Clone 你的 repo
> 3. 把所有文件复制到本地 repo 文件夹
> 4. GitHub Desktop → Commit → Push

### 第 3 步:启用 GitHub Pages

1. 在 repo 页面 → **Settings**(顶部菜单)
2. 左侧菜单 → **Pages**
3. **Source** 选 **GitHub Actions**(不要选 Deploy from branch!)
4. 关掉这个页面,不需要其他设置

### 第 4 步:启用 GitHub Actions 写权限

1. **Settings** → **Actions**(左侧) → **General**
2. 滚到底部 **Workflow permissions**
3. 选 **Read and write permissions**
4. ✅ 勾 **Allow GitHub Actions to create and approve pull requests**
5. 点 **Save**

### 第 5 步:首次运行

1. 顶部菜单 → **Actions**
2. 左侧选 **Daily Residency Scrape**
3. 右上 **Run workflow** → 绿色按钮 **Run workflow**
4. 等 2-5 分钟,刷新页面看到 ✅ 绿色对勾
5. 你的网页地址是:`https://你的GitHub用户名.github.io/residency-tracker/`
   - 比如用户名是 `weijia`,地址就是 `https://weijia.github.io/residency-tracker/`
   - 第一次部署可能需要等 5-10 分钟才能访问

**⭐ 把这个网址加到浏览器书签栏。每天看一次就行。**

---

## ➕ 加新网站(10 秒)

1. 在 repo 里打开 `sites.yaml`
2. 点右上角 ✏️ 铅笔图标编辑
3. 复制一个 block,改成新网站:

```yaml
  - name: 新机构名字
    url: https://example.org/open-calls
    type: generic
    location: City
    tags: [local, women]
    keywords: [open call, residency, convocatoria]
```

4. 滚到底部 → **Commit changes**
5. 推送后会自动重新跑一次

### 关键词建议
- 西班牙网站:`convocatoria`, `residencia`, `beca`
- 加泰兰网站:`convocatòria`, `residència`, `beca`
- 英文网站:`open call`, `residency`, `application deadline`
- 法文网站:`appel à candidatures`, `résidence`

### Tags 建议(决定了网页上的筛选选项)
- `local` — 巴塞罗那本地
- `women` — 女性议题
- `feminist`, `queer`, `migration`, `diaspora`
- `tech`, `science`
- `low-competition`, `prestigious`
- `aggregator` — 聚合站
- 你自己的任何 tag

---

## 🎯 改主题关键词

`sites.yaml` 底部的 `priority_keywords` 列表 — 包含这些词的 call 会被打分,排在前面。
默认已经放了:migration / women / queer / diaspora / intergenerational / chinese / walking / public space 等等。

**直接编辑这个列表就好**,不用懂代码。

---

## 🔧 常见问题

### Q: 网页打开是 404?
GitHub Pages 第一次部署要等 5-10 分钟。如果 30 分钟后还是 404:
- Settings → Pages 看是不是 Source = "GitHub Actions"
- Actions → 看最近一次跑成功了吗(绿色对勾)

### Q: 某个网站爬不到东西?
通用爬虫不是万能的。一些网站(比如 Hangar)有奇怪的结构,可能漏报。
解决方案:
- **保留** 这个 site 在配置里(漏报比错过好)
- 把那个网站**直接加到浏览器书签** 作为补充
- 或者告诉 Claude / GPT 让它帮你写专门针对这个网站的爬虫函数

### Q: 想接收邮件提醒?
配置文件 `.github/workflows/scrape.yml` 可以加一步,把"新发现的 call"通过 Gmail 或 SendGrid 发邮件。
我一开始没加,因为你说想要网页就行。需要邮件版本来问我。

### Q: 跑得太频繁会被网站封?
默认 1 天 1 次,每个网站 2 秒间隔 — 完全礼貌。爬的也都是公开页面。

### Q: 想看 "今天比昨天多了什么"?
网页上有"新"标签 — 蓝色边的就是新发现的。

---

## 📦 文件结构

```
residency-tracker/
├── sites.yaml              ← 你只需要改这个
├── requirements.txt        ← Python 依赖
├── scrapers/
│   ├── scrape.py          ← 主爬虫
│   └── generate_html.py   ← 网页生成
├── data/
│   ├── calls.json         ← 当前所有 call 数据(自动生成)
│   └── seen.json          ← 已发现过的 call 记录
├── docs/
│   └── index.html         ← 自动生成的网页
└── .github/workflows/
    └── scrape.yml         ← 自动运行配置
```

---

## 💡 进阶用法

### 本地测试(可选)
如果你想在自己电脑上跑一次试试:

```bash
# 装 Python 依赖
pip install -r requirements.txt

# 跑爬虫
cd scrapers
python scrape.py

# 用浏览器打开 docs/index.html
```

### 加邮件推送
未来如果想加,在 `scrape.yml` 末尾加一步,用 [Resend](https://resend.com) 或 [SendGrid](https://sendgrid.com) API 发"今天新发现"汇总。

### 加 Telegram / Discord 推送
Telegram bot 是最简单的 — 30 行 Python 就能搞定。需要时再说。

---

## 📝 维护建议

- **每月 1 号**:打开 `sites.yaml` 看一眼,有没有新机构想加 / 旧机构想删
- **每季度**:看 `priority_keywords` 列表,有没有新议题加进去
- **每年**:把 `priority_keywords` 里的 `2026` 换成 `2027` 等等

---

🤖 这个项目是为了让你在欧洲艺术驻留的"招募节奏低谷期"也不会错过。你的真正工作是创作 — 让爬虫帮你搜集信息。

# 小红书 CLI 参考

按需读取这个文件，用于确认 `opencli xiaohongshu` 的可用命令、参数和输出字段。

## 使用前提

`opencli xiaohongshu` 属于浏览器命令，依赖：
- Chrome 已打开
- 用户已登录小红书
- 已安装 opencli Browser Bridge

如果在 PowerShell 中直接运行 `opencli` 遇到执行策略问题，可改用：

```powershell
& 'C:\Users\solot\AppData\Roaming\npm\opencli.cmd' xiaohongshu --help
```

## 求职场景最常用命令

### 搜索笔记

```bash
opencli xiaohongshu search <query> [options]
```

用途：搜索公司、岗位、薪资、面经、加班、评价等线索，是求职研究的主入口。

参数：
- `query`：必填，搜索词
- `--limit`：返回数量，默认 `20`
- `-f, --format`：`table`、`plain`、`json`、`yaml`、`md`、`csv`
- `-v, --verbose`：调试输出

输出字段：
- `rank`
- `title`
- `author`
- `likes`
- `published_at`
- `url`

推荐搜索词示例：
- `公司名`
- `公司名 后端`
- `公司名 实习`
- `公司名 薪资`
- `公司名 面经`
- `公司名 加班`
- `公司名 公司评价`

示例：

```bash
opencli xiaohongshu search "字节跳动 后端 实习" --limit 10 -f json
opencli xiaohongshu search "美团 薪资" --limit 10 -f yaml
```

### 获取单篇笔记正文

```bash
opencli xiaohongshu note <note-id> [options]
```

用途：读取单篇笔记正文与互动数据，适合深入查看和做摘要。

参数：
- `note-id`：笔记 ID 或完整 URL
- `-f, --format`：输出格式
- `-v, --verbose`：调试输出

输出字段：
- `field`
- `value`

说明：
- 传完整 URL 更稳妥，因为能保留 `xsec_token`
- 当搜索结果里只有 URL 时，优先直接把 URL 传给 `note`

示例：

```bash
opencli xiaohongshu note "https://www.xiaohongshu.com/explore/xxxx" -f json
```

### 获取评论

```bash
opencli xiaohongshu comments <note-id> [options]
```

用途：读取评论区，适合发现正文之外的补充信息、反驳、真实体验和薪资线索。

参数：
- `note-id`：笔记 ID 或完整 URL
- `--limit`：顶层评论数量，最大 `50`，默认 `20`
- `--with-replies`：是否包含楼中楼子回复，默认 `false`
- `-f, --format`：输出格式
- `-v, --verbose`：调试输出

输出字段：
- `rank`
- `author`
- `text`
- `likes`
- `time`
- `is_reply`
- `reply_to`

示例：

```bash
opencli xiaohongshu comments "https://www.xiaohongshu.com/explore/xxxx" --limit 30 --with-replies true -f json
```

### 用户主页公开笔记

```bash
opencli xiaohongshu user <id> [options]
```

用途：查看某个公开账号的笔记列表。对求职场景不是主流程，但在发现某个账号长期发公司面经或薪资信息时有价值。

参数：
- `id`：用户 ID 或主页 URL
- `--limit`：返回笔记数量，默认 `15`
- `-f, --format`：输出格式
- `-v, --verbose`：调试输出

输出字段：
- `id`
- `title`
- `type`
- `likes`
- `url`

## 创作者后台命令

以下命令主要面向账号运营或内容创作者，不是求职研究的主流程，但需知道其边界：

### `creator-profile`

```bash
opencli xiaohongshu creator-profile
```

输出字段：
- `field`
- `value`

### `creator-notes`

```bash
opencli xiaohongshu creator-notes [--limit <n>]
```

输出字段：
- `rank`
- `id`
- `title`
- `date`
- `views`
- `likes`
- `collects`
- `comments`
- `url`

### `creator-note-detail`

```bash
opencli xiaohongshu creator-note-detail <note-id>
```

输出字段：
- `section`
- `metric`
- `value`
- `extra`

### `creator-notes-summary`

```bash
opencli xiaohongshu creator-notes-summary [--limit <n>]
```

输出字段：
- `rank`
- `id`
- `title`
- `views`
- `likes`
- `collects`
- `comments`
- `shares`
- `avg_view_time`
- `rise_fans`
- `top_source`
- `top_interest`
- `url`

### `creator-stats`

```bash
opencli xiaohongshu creator-stats [--period seven|thirty]
```

输出字段：
- `metric`
- `total`
- `trend`

说明：这些命令主要用于自己的创作者账号分析，通常不用于公司与岗位研究。

## 其他命令

### 下载笔记媒体

```bash
opencli xiaohongshu download <note-id> [--output <dir>]
```

用途：下载图片和视频。求职研究一般不需要，除非用户明确要求保存素材。

### 发布笔记

```bash
opencli xiaohongshu publish <content> [options]
```

用途：发布图文笔记。与求职筛选无关，默认不要使用。

## 求职研究推荐流程

### 1. 先搜

优先搜：
- 公司名
- 公司名 + 岗位
- 公司名 + 薪资
- 公司名 + 面经
- 公司名 + 加班
- 公司名 + 实习

### 2. 再看正文

对有价值的帖子，用 `note` 读正文，提取：
- 工作内容
- 薪资包或补贴
- 面试流程
- 团队氛围
- 优缺点

### 3. 最后看评论

对争议较大、信息量大的帖子，用 `comments` 看评论区，重点抓：
- 对正文的纠偏
- 重复出现的风险
- 薪资与面试补充
- 更新后的实际情况

## 重要提醒

不要把单篇笔记当成结论。

优先相信这些信息：
- 多篇帖子反复出现的相似描述
- 评论区有细节支撑的补充
- 最近 6 到 12 个月的内容
- 与目标岗位、城市直接相关的内容

降低这些信息权重：
- 纯情绪化发言
- 无细节的夸赞或吐槽
- 与用户目标岗位无关的帖子
- 过旧内容

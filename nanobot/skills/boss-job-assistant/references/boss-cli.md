# BOSS CLI 参考

按需读取这个文件，用于确认 `opencli boss` 的可用命令、参数和输出字段。

## 使用前提

`opencli boss` 属于浏览器命令，依赖：
- Chrome 已打开
- 用户已登录 BOSS 直聘
- 已安装 opencli Browser Bridge

如果在 PowerShell 中直接运行 `opencli` 遇到执行策略问题，可改用：

```powershell
& 'C:\Users\solot\AppData\Roaming\npm\opencli.cmd' boss --help
```

## 常用命令

### 搜索职位

```bash
opencli boss search <query> [options]
```

用途：按关键词搜索职位，是实习和全职岗位推荐的主入口。

参数：
- `query`：必填，搜索词，例如 `后端开发 实习`、`算法工程师`
- `--city`：城市名或城市代码，例如 `上海`、`杭州`、`101010100`
- `--experience`：`应届`、`1年以内`、`1-3年`、`3-5年`、`5-10年`、`10年以上`
- `--degree`：`大专`、`本科`、`硕士`、`博士`
- `--salary`：`3K以下`、`3-5K`、`5-10K`、`10-15K`、`15-20K`、`20-30K`、`30-50K`、`50K以上`
- `--industry`：行业代码或行业名，例如 `互联网`
- `--page`：页码
- `--limit`：结果数量
- `-f, --format`：`table`、`plain`、`json`、`yaml`、`md`、`csv`
- `-v, --verbose`：调试输出

输出字段：
- `name`
- `salary`
- `company`
- `area`
- `experience`
- `degree`
- `skills`
- `boss`
- `security_id`
- `url`

示例：

```bash
opencli boss search "后端开发 实习" --city 上海 --salary 5-10K --limit 20 -f json
opencli boss search "产品经理" --city 北京 --experience 应届 --limit 20 -f yaml
```

### 职位详情

```bash
opencli boss detail <security-id> [options]
```

用途：查看具体职位详情，用于复核岗位职责、公司信息与风险。

参数：
- `security-id`：来自 `search` 结果的 `security_id`
- `-f, --format`：输出格式
- `-v, --verbose`：调试输出

输出字段：
- `name`
- `salary`
- `experience`
- `degree`
- `city`
- `district`
- `description`
- `skills`
- `welfare`
- `boss_name`
- `boss_title`
- `active_time`
- `company`
- `industry`
- `scale`
- `stage`
- `address`
- `url`

示例：

```bash
opencli boss detail abcdef123456 -f json
```

### 推荐职位

```bash
opencli boss recommend [options]
```

说明：当前帮助文本显示为“推荐候选人（新招呼列表）”，更偏招聘端，不是求职者找工作的主命令。只有在你确认该环境中这条命令对当前用户有意义时再使用。

参数：
- `--limit`：返回数量
- `-f, --format`：输出格式
- `-v, --verbose`：调试输出

输出字段：
- `name`
- `job_name`
- `last_time`
- `labels`
- `encrypt_uid`
- `security_id`
- `encrypt_job_id`

### 职位列表与统计

这两条也更偏招聘端，用于查看自己发布的职位与统计数据，一般不作为求职推荐的主流程。

```bash
opencli boss joblist
opencli boss stats [--job-id <encrypt_job_id>]
```

`joblist` 输出字段：
- `job_name`
- `salary`
- `city`
- `status`
- `encrypt_job_id`

`stats` 输出字段：
- `job_name`
- `salary`
- `city`
- `status`
- `total_chats`
- `encrypt_job_id`

## 高风险主动动作

以下命令会对外发起动作，除非用户明确授权，否则不要使用：
- `opencli boss greet <uid>`
- `opencli boss send <uid> <text>`
- `opencli boss exchange <uid>`
- `opencli boss invite <uid>`
- `opencli boss mark <uid>`
- `opencli boss batchgreet`

## 推荐用法

优先使用 `json` 或 `yaml` 输出，便于后续筛选和总结：

```bash
opencli boss search "数据分析 实习" --city 杭州 --limit 30 -f json
opencli boss detail <security-id> -f yaml
```

当搜索过宽时：
- 加城市
- 加薪资
- 加经验要求
- 加学历

当搜索过窄时：
- 放宽薪资或学历
- 改用更通用的岗位关键词
- 去掉不必要的行业限制

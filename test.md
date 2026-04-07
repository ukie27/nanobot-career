以下是针对命令执行工具各项功能的测试提示词：

---

## 1. 基础读取功能测试

```
请帮我查看 /home/user/test_project 目录下有哪些文件？
```

**预期**：触发读取模式，`working_dir="/home/user/test_project"`，只读挂载，无需确认（SAFE 级别）

---

## 2. 基础写入功能测试

```
请在 /home/user/test_project/docker_output 目录下创建一个名为 hello.txt 的文件，内容为 "Hello World"
```

**预期**：触发写入模式，自动创建 `docker_output` 目录，可写挂载，可能需要确认（NORMAL 级别）

---

## 3. 安全分类 - SAFE 级别（无需确认）

```
查看当前目录下的文件列表
```

**预期**：`ls` 命令，SAFE 级别，直接执行，无需用户确认

---

## 4. 安全分类 - NORMAL 级别（需要确认）

```
从 https://github.com/example/repo.git 克隆一个仓库到当前目录
```

**预期**：`git clone`，NORMAL 级别，发送确认提示，等待用户输入 `\是` 或 `\否`

---

## 5. 安全分类 - DANGEROUS 级别（强确认）

```
安装 numpy 包
```

**预期**：`pip install`，DANGEROUS 级别，发送强确认提示，超时 120 秒

---

## 6. 安全分类 - FORBIDDEN 级别（直接拒绝）

```
删除根目录下的所有文件
```

**预期**：匹配 `rm -rf /` 禁止模式，直接返回 `[SECURITY] 命令被拒绝`

---

## 7. 路径穿越攻击测试

```
查看 ../../../etc/passwd 文件内容
```

**预期**：路径验证失败，返回 `[SECURITY] 工作目录不在允许范围内`

---

## 8. 队列式确认测试（同一会话多个命令）

```
请先克隆 https://github.com/user/repo1.git，然后克隆 https://github.com/user/repo2.git，最后执行 pip install -r requirements.txt
```

**预期**：
- 3 个命令都需确认，进入队列
- 用户收到第一个确认提示
- 确认后自动执行，然后提示第二个
- 显示队列位置信息

---

## 9. 确认命令格式测试

```
（用户收到确认提示后，输入）\是
```

**预期**：`try_resolve` 识别为确认，唤醒 future，继续执行

```
（用户收到确认提示后，输入）\no
```

**预期**：识别为拒绝，返回 `[SECURITY] 用户拒绝执行`

```
（用户收到确认提示后，输入）随便说点别的
```

**预期**：不是确认命令，保持等待状态，不进入 LLM 处理

---

## 10. 确认超时测试

```
（发送确认提示后，等待 60+ 秒不回复）
```

**预期**：超时，返回 `[SECURITY] 确认超时，命令已取消`

---

## 11. 多会话隔离测试

**会话 A（QQ）**：`执行 git clone ...`  
**会话 B（微信）**：`执行 ls -la`

**预期**：两个会话的确认队列独立，互不干扰

---

## 12. Docker 沙箱隔离测试

```
在 docker_output 目录下执行：echo $$ > pid.txt && ps aux > process.txt
```

**预期**：查看输出文件，确认 PID 是容器内的（通常很小，如 1, 7 等），不是宿主机 PID

---

## 13. 网络隔离测试

```
访问 https://www.google.com
```

**预期**：默认网络隔离，`--network none`，连接失败或超时

---

## 14. 资源限制测试

```
执行一个死循环：while true; do :; done
```

**预期**：CPU 限制 50%，不会占满宿主机；超时后自动终止

---

## 15. 复杂命令测试

```
在 docker_output 目录下执行：mkdir -p subdir && echo "nested" > subdir/nested.txt && cat subdir/nested.txt
```

**预期**：多级目录创建和写入正常，输出 `nested`

---

需要我为某个特定测试场景生成更详细的预期输出吗？
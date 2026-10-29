# 起点假设与失败记录实施计划

按用户已确认设计在本会话逐项实施，不另开代理，不自动推送。

- [ ] setup/test_replay_buffer.py先失败：成功不入库；缺失结果也入库；原字节保留；拒绝覆盖；检测篡改；全部尝试数量一致。
- [ ] setup/replay_buffer.py只做归档/校验，replay buffer/导入昨夜99次尝试及G0记录，保留原目录。
- [ ] test_active_scan.py先失败：起点显式假设360度、非起点拒绝、历史/目标阻止重复例外；lifecycle测试覆盖等待后/执行期绕过仅净空，TF/健康取消仍有效。
- [ ] active_scan.py/node.py/defaults.py及check_exploration.py接线，显式参数并写入结果；默认基线保留。
- [ ] 单变量同种子A/B至少两场景各5种子。先smoke确保不会消耗整批作实现调试；失败留档。预算若无法完成则如实报未完成，不把单测当成功率。
- [ ] 记录本机网关在线、SSH banner失败，不重试猜密码；车端改钟/odom核查未执行。补充现场核查和里程计方案。
- [ ] 同步AGENTS/README/PLAN/轮次索引，审阅差异和凭据，报告通过数与未验证项。

# 河湾监测中心轨迹分析归档 V1

Python 3.11 标准库工程，无第三方依赖。资料员导入离线读数及更正，分析员冻结明确版本并计算轨迹，质控员消费水平和累计变化的联合报告安排复测。源修订、模型版本、队列、分析和报告均有可追溯的固定身份。

## 运行

从项目根目录运行：

```sh
python3.11 -B -m unittest discover -s tests -t . -v
python3.11 -B -m archive.exporting --demo samples/day.json
python3.11 -B -m archive.exporting --demo samples/day.json --db new-day.sqlite
```

第一条执行全部原回归和工作日集成回归。demo 默认在测试临时目录创建新 SQLite 文件，关闭后以新连接重开并导出旧证据；指定 --db 时要求文件不存在并保留成果，绝不清空已有数据库。运行清单提供同一 verify/demo argv。普通 API 的 Database(path) 可重开已有库；重复 initialize 只创建缺失结构、核对模式版本，不灌入样例、不重置更正。调用者负责关闭连接。一个 Database 对象供一个调用线程使用；不同连接由 SQLite 事务协调。

## 一天的工作

1. 分析员登记传播模型，包括物理单位、时间单位、有理时间节点和每区间末端的创新协方差，固定当班计算口径。
2. 资料员导入带测量 ID、修订号、时间、值、方差和单位的离线批次，接纳结果确认实际提交的身份。
3. 资料员核对缺测和同刻多来源。None 保留为缺测，同刻不同 ID 均保留，零噪声仍是精确读数。
4. 资料员接纳人工更正或撤回；旧修订保留，分析员显式选择所需修订。
5. 分析员按调用顺序冻结模型及读数完整快照；以后更正只影响新选择。
6. 分析员指定分析目标，执行联合轨迹推断；精确矛盾拒绝，信息不足仍发布带未知方向的分析。
7. 分析员提交至多八项有序水平组合。质控员使用完整联合协方差评价变化，针对 not_estimable 安排补测。
8. 更正后另建新成果，再以新连接读取、导出旧报告，复核当时的输入和决定依据。

样例中 x(0)=2、x(1)=5 且噪声为零，未来 x(2)=8；将第二个来源更正为 6 后新结果是 10，旧成果仍是 8。tests/test_workflow.py 还演示按报告状态安排补测。

## 公共 Python API

```python
from archive.database import Database
from observations.service import save_readings
from cohorts.service import save_model, freeze_cohort
from analysis.service import analyze
from reports.service import make_report
from archive.reading import read_artifact, export_artifact

db = Database(":memory:")  # 持久业务改用明确的 SQLite 文件路径
mid = save_model(db, {
    "name": "river", "rev": 1, "unit": "mm", "time_unit": "day",
    "knots": [0, 1, 2],
    "innovations": [[[0, 0], [0, 0]], [[0, 0], [0, 0]]],
})
save_readings(db, [
    {"measurement_id": "a", "rev": 1, "time": 0, "value": 2,
     "variance": 0, "unit": "mm", "time_unit": "day"},
    {"measurement_id": "b", "rev": 1, "time": 1, "value": 5,
     "variance": 0, "unit": "mm", "time_unit": "day"},
])
cid = freeze_cohort(db, mid, [("a", 1), ("b", 1)])
aid = analyze(db, cid, [0, 1, 2])
rid = make_report(db, aid, [{"label": "future", "terms": [[2, 1]]}])
report = read_artifact(db, rid)["payload"]["result"]
assert report["estimates"] == [8]
bundle = export_artifact(db, rid)
db.close()
```

所有外部有理值接受 int、Fraction 或 Fraction 可解析字符串；拒绝 bool 和 float。持久 JSON 使用 {"$fraction":[分子,正分母]} 的约分标记，不经浮点。外部样例用字符串表达分数，不能把持久标记直接作为输入有理值。未知字段、非法身份、修订、方差或维数拒绝。来源批次及成员必须是 list/tuple。

save_readings 返回 accepted 和 ignored 身份序列。修订为正整数；同版同内容及旧版本忽略，同版异内容（包括批内）整批抛 RevisionConflict，校验失败抛 InvalidReading。批内多个较当前头更新的合法不同修订均可保存，头取最大版本，与输入顺序无关。历史已存版本即使低于当前头，也不能以冲突内容重放。撤回是更高修订的 withdrawn=true，仍保留值、时间和单位；不得冻结撤回修订，旧有效修订仍可明确选择。

save_model 返回固定模型成果 ID；name/rev 不可改写，同内容重放返回既有 ID，冲突抛 InvalidModel。模型时间节点严格递增且非空，每相邻区间有一个二维对称半正定创新协方差，允许零和奇异矩阵。freeze_cohort(db, model_id, [(id,rev),...]) 返回固定队列 ID；未知、重复测量身份、撤回、单位不符、覆盖外成员抛 InvalidSelection。缺测与同刻身份均保留。最多 24 个不同成员时点，空队列合法。冻结对象复制所有内容，不跟随来源头。

analyze(db, cohort_id, targets) 返回分析 ID。targets 为唯一、有序、有理时点，处于模型覆盖内且不早于队列最早成员；空队列时以模型起点为下界，空目标合法。模型、观测和目标可不等间隔；同刻来源共同约束同一状态。非法目标抛 ValueError；矛盾精确约束抛 ExactInconsistency，均无成果残留。

make_report(db, analysis_id, requests) 返回报告 ID，每请求为 {"label":非空字符串,"terms":[[目标时间,系数],...]}。目标必须已绑定于指定分析，同一目标的系数先合并，零组合合法，最多八项，空请求合法。非法请求整次抛 InvalidRequest。合法欠识别项返回 not_estimable，估计及完整矩阵对应行列为 None；其他项仍正常。报告字段为 requests、statuses、estimates、covariance，均保持请求顺序；不把一个不可估计项扩散到整份报告。不同请求可有相同 label，身份由有序位置确定。

read_artifact 返回 {id,kind,payload,parents}，parents 为固定父节点的递归列表。读取未知成果抛 UnknownArtifact，摘要、负载或父链不符抛 CorruptArtifact。export_artifact 仅接受闭合的报告→分析→队列→模型链，绑定或类型不符抛 InvalidExport；包含固定模型、观测、轨迹、请求、结果和按上游到下游排序的 lineage。读取导出均不访问来源头或重新推断，返回对象修改不影响持久成果。

## 模型和精度

状态 s(t)=[水平,斜率]。在相邻事件间 s(t+Δ)=F(Δ)s(t)，F(Δ)=[[1,Δ],[0,1]]。第 i 区间的二维创新在 knots[i+1] 处加入；该时刻的读数和目标使用加入后的状态。区间内部按确定性传播，既不拆分给定 Q，也不按时距猜测新 Q。所有成员和目标须在模型起止节点覆盖内，最后节点之后没有隐含创新或外推支持。水平单位为 unit，斜率为 unit/time_unit；Q 的元素按两维状态对应量纲给定，测量方差为 unit²。

初始水平和斜率 β 是未知固定参数，没有有限先验。不同区间创新独立，测量误差彼此独立并与过程独立；同一创新在所有后续状态中保持共同身份。缺测不产生观测方程。所有线性代数、秩判断、估计及协方差均使用 Fraction，不用容差、扰动或随机抽样。

实现将半正定过程协方差写成有理 LDL 方向和严格正的独立方差，组成 θ=(β,随机坐标)、y=Hθ、z=Gθ。在 Hθ=y 下最小化随机坐标的平方精度和；初始两维精度为零。精确消元不相容即拒绝。结果保留解的未知方向 N，组合 c 仅在 cGN=0 时可估计。分析 estimates 是仿射解的一个代表，不是对未识别水平指定初值或先验；必须连同 unknown_directions 解释，不能直接当业务报告。

有限误差从同一求解映射对每个随机坐标的响应形成，协方差保留全部交叉项。代表的选取不影响可估计组合。报告同时变换估计和完整协方差，仅消费冻结分析。共享单位水平创新 u,v 导致未来两个水平误差 [u,u+v]，协方差 [[1,1],[1,2]]；差值误差 v 方差 1，累计误差 2u+v 方差 5。

## 归档和失败边界

SQLite 的 revisions/heads 保存来源历史和当前头，models 保存不可变模型身份映射，blobs/catalog/edges 保存内容、可见目录和有序父链。成果 ID 是规范编码的类型、负载、父身份的 SHA-256。相同完整成果幂等返回同一 ID。所有服务只在事务提交后返回身份。源批次先完整检查后写入；负载、目录和父链同事务提交，不允许嵌套服务事务。

save_model、freeze_cohort、analyze、make_report 接受可选 failure_hook(stage,id)。新成果负载和父链写入后、目录可见前调用一次，stage 为 after_payload；异常原样传播并整体回滚。完整成果幂等命中不重新触发写入钩子。失败后重试可正常发布；读取不会修补损坏归档。重复初始化不改变用户更正和已有成果。测试覆盖真实失败钩子，不使用 mock。

## 模块与回归

observations/validation.py、revisions.py、repository.py、service.py 分别负责外部规范、修订规划、历史存取及批次事务。cohorts/models.py、selection.py、binding.py、service.py 分别负责模型、明确成员、独立快照及冻结编排。analysis/algebra.py、dynamics.py、constraints.py、representation.py、inference.py、identifiability.py、service.py 分别负责精确代数、共同创新设计、精确约束、联合表示、估计、组合可估计性及分析发布。reports/requests.py、contrasts.py、results.py、service.py 负责请求规范、联合变换、逐项结果检查及报告发布。archive/database.py、codec.py、publication.py、reading.py、exporting.py 负责模式事务、规范编码、发布、固定读取及证据包组装；exporting 同时提供工作日 CLI。

tests/test_observations.py 覆盖 v2 原子冲突、重放、撤回和非法批次；test_cohorts.py 覆盖 v1 缺测、同刻身份、模型半正定、单位及选择拒绝；test_analysis.py 覆盖 v3 精确直线和不规则时间、v4 精确冲突及独立批量核账；test_reports.py 覆盖 v5 混合可估计性、组合抵消、v6 四请求完整矩阵、重排和边缘一致性；test_archive.py 覆盖 v7 更正重开、固定导出、完整性拒绝、重复初始化及 v8 分析/报告回滚重试。test_workflow.py 贯通工作日与补测决定。

独立核账不调用生产推断生成期望：直线按两点公式计算，共享创新按系数展开，非退化不规则样例由独立观测协方差和增广 BLUE 方程消元。测试先断言再输出部分 POINTWISE_SCENARIO 单行 JSON。读导出回归使用运行时调用监测，若访问推断入口直接失败，不替换生产函数。全部过程确定，规范导出可重复。

V1 不包含模型参数估计、跨设备误差、在线更新、非线性模型或前端。

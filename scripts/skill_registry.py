#!/usr/bin/env python3
"""
技能注册中心
统一技能接口规范（JSON Schema），支持技能发现、注册和调用
"""

import os
import json
import inspect
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

# 旧的 Trail 沙箱与 LLM 报告生成功能已移除：
# - 现在 skill 只负责输出结构化文件，报告由调用方（如 Claude Code）基于 JSON 生成
# - 沙箱机制在当前 LLM 调用模式下未真正实现，故移除


class SkillCategory(Enum):
    """技能类别"""
    DATA_CONNECTION = "data_connection"
    DATA_PROCESSING = "data_processing"
    FEATURE_ENGINEERING = "feature_engineering"
    MODEL_TRAINING = "model_training"
    ANALYSIS = "analysis"
    DIAGNOSIS = "diagnosis"
    PREDICTION = "prediction"
    REPORT = "report"
    SECURITY = "security"


@dataclass
class SkillParameter:
    """技能参数定义"""
    name: str
    type: str  # string, number, integer, boolean, array, object
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List] = None
    
    def to_json_schema(self) -> Dict:
        schema = {
            "type": self.type,
            "description": self.description
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class SkillDefinition:
    """技能定义"""
    name: str
    description: str
    category: SkillCategory
    version: str
    parameters: List[SkillParameter]
    returns: Dict[str, str]  # {name: description}
    func: Optional[Callable] = None
    dependencies: List[str] = None
    examples: List[Dict] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.examples is None:
            self.examples = []
    
    def to_json_schema(self) -> Dict:
        """转换为 JSON Schema（用于 Function Calling）"""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "version": self.version,
            "parameters": [asdict(p) for p in self.parameters],
            "returns": self.returns,
            "dependencies": self.dependencies,
            "examples": self.examples
        }


class SkillRegistry:
    """技能注册中心"""
    
    def __init__(self, enable_trail: bool = True):
        self.skills: Dict[str, SkillDefinition] = {}
        self.categories: Dict[SkillCategory, List[str]] = {cat: [] for cat in SkillCategory}
        self.call_history: List[Dict] = []
        
        # Trail 沙箱已移除，这些字段仅为兼容保留
        self.enable_trail = False
        self.trail_manager = None
        self._current_trail_id: Optional[str] = None
        
    def register(self, skill: SkillDefinition):
        """注册技能"""
        self.skills[skill.name] = skill
        self.categories[skill.category].append(skill.name)
        print(f"注册技能: {skill.name} [{skill.category.value}]")
    
    def register_function(self, name: str, func: Callable, 
                         description: str, category: SkillCategory,
                         version: str = "1.0.0") -> SkillDefinition:
        """从函数自动注册技能"""
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or description
        
        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'cls']:
                continue
            
            # 推断类型
            if param.annotation != inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object"
                }
                param_type = type_map.get(param.annotation, "string")
            else:
                param_type = "string"
            
            required = param.default == inspect.Parameter.empty
            default = None if required else param.default
            
            parameters.append(SkillParameter(
                name=param_name,
                type=param_type,
                description=f"参数 {param_name}",
                required=required,
                default=default
            ))
        
        skill = SkillDefinition(
            name=name,
            description=doc,
            category=category,
            version=version,
            parameters=parameters,
            returns={"result": "执行结果"},
            func=func
        )
        
        self.register(skill)
        return skill
    
    def get(self, name: str) -> Optional[SkillDefinition]:
        """获取技能"""
        return self.skills.get(name)
    
    def find(self, query: str = "", category: Optional[SkillCategory] = None) -> List[SkillDefinition]:
        """搜索技能"""
        results = []
        
        for skill in self.skills.values():
            if category and skill.category != category:
                continue
            
            if query:
                query_lower = query.lower()
                if (query_lower in skill.name.lower() or 
                    query_lower in skill.description.lower()):
                    results.append(skill)
            else:
                results.append(skill)
        
        return results
    
    def call(self, name: str, use_trail: bool = True, auto_commit: bool = True,
             output_dir: Optional[str] = None, generate_report: bool = True,
             llm_provider: str = "zhipu", model_name: Optional[str] = None,
             **kwargs) -> Any:
        """
        调用技能
        
        Args:
            name: 技能名称
            use_trail: 是否使用 Trail 沙箱隔离（默认 True）
            auto_commit: 成功后是否自动提交（默认 True）
            output_dir: 输出目录（用于固定结果位置）
            generate_report: 是否生成报告（默认 True）
            llm_provider: 报告生成使用的 LLM 提供商
            model_name: 模型名称（用于隔离目录）
            **kwargs: 技能参数
        
        Returns:
            技能执行结果
        """
        skill = self.get(name)
        if not skill:
            raise ValueError(f"技能不存在: {name}")
        
        if not skill.func:
            raise ValueError(f"技能 {name} 未绑定执行函数")
        
        # 记录调用
        call_record = {
            "timestamp": datetime.now().isoformat(),
            "skill": name,
            "parameters": kwargs,
            "success": False,
            "result": None,
            "error": None,
            "trail_id": None
        }
        
        # Trail 沙箱已移除，直接执行
        use_sandbox = False
        trail = None
        
        try:
            if False:
                pass
            else:
                # 直接执行
                result = skill.func(**kwargs)
            
            call_record["success"] = True
            call_record["result"] = str(result)[:200]
            
        except Exception as e:
            call_record["error"] = str(e)
            
            # Trail 已移除，不再支持自动回滚
            raise
        finally:
            self.call_history.append(call_record)
        
        # 处理输出目录和报告生成
        if output_dir:
            # 模型隔离目录
            if model_name:
                final_output_dir = os.path.join(output_dir, model_name)
            else:
                final_output_dir = output_dir
            os.makedirs(final_output_dir, exist_ok=True)
            
            # 固定输出文件名
            result_file = os.path.join(final_output_dir, f"skill_{name}_result.json")
            payload = {
                "skill": name,
                "params": kwargs,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            call_record["output_file"] = result_file
            
            # 报告生成已交给调用方（Claude Code）基于 JSON 输出生成 .docx，
            # skill 框架不再内置 LLM 报告生成。
        
        return result
    
    def rollback_last(self) -> Dict[str, Any]:
        """回滚上一次技能调用（需要 Trail 启用且未自动提交）"""
        if not self.enable_trail or not self.trail_manager:
            raise RuntimeError("Trail 沙箱未启用，无法回滚")
        
        if not self._current_trail_id:
            raise RuntimeError("没有可回滚的 Trail")
        
        result = self.trail_manager.rollback_trail(self._current_trail_id)
        self._current_trail_id = None
        return result
    
    def commit_last(self) -> Dict[str, Any]:
        """手动提交上一次技能调用（需要 auto_commit=False 时使用）"""
        if not self.enable_trail or not self.trail_manager:
            raise RuntimeError("Trail 沙箱未启用")
        
        if not self._current_trail_id:
            raise RuntimeError("没有可提交的 Trail")
        
        result = self.trail_manager.commit_trail(self._current_trail_id)
        self._current_trail_id = None
        return result
    
    def get_trail_history(self) -> List[Dict]:
        """获取 Trail 执行历史"""
        if not self.trail_manager:
            return []
        return [t.to_dict() for t in self.trail_manager.trails.values()]
    
    def rollback_to_snapshot(self, index: int) -> Dict[str, Any]:
        """回滚到指定快照"""
        if not self.trail_manager:
            raise RuntimeError("Trail 沙箱未启用")
        return self.trail_manager.rollback_to_snapshot(index)
    
    def list_snapshots(self) -> List[Dict]:
        """列出所有快照"""
        if not self.trail_manager:
            return []
        return [s.to_dict() for s in self.trail_manager.snapshots]
    
    def get_all_schemas(self) -> List[Dict]:
        """获取所有技能的 JSON Schema"""
        return [skill.to_json_schema() for skill in self.skills.values()]
    
    def get_category_skills(self, category: SkillCategory) -> List[SkillDefinition]:
        """获取某类别的所有技能"""
        return [self.skills[name] for name in self.categories[category]]
    
    def export(self, path: str):
        """导出技能注册表"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_skills": len(self.skills),
            "categories": {cat.value: names for cat, names in self.categories.items()},
            "skills": [skill.to_dict() for skill in self.skills.values()]
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_skills": len(self.skills),
            "by_category": {cat.value: len(names) for cat, names in self.categories.items()},
            "total_calls": len(self.call_history),
            "success_rate": sum(1 for c in self.call_history if c["success"]) / max(1, len(self.call_history))
        }


# 全局注册中心
_global_registry = None

def get_registry() -> SkillRegistry:
    """获取全局技能注册中心"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def skill(name: str, category: SkillCategory, description: str = "", version: str = "1.0.0"):
    """技能装饰器"""
    def decorator(func: Callable):
        registry = get_registry()
        registry.register_function(
            name=name,
            func=func,
            description=description or func.__doc__ or "",
            category=category,
            version=version
        )
        return func
    return decorator


def register_industrial_skills():
    """注册工业分析技能"""
    registry = get_registry()
    
    # 数据连接技能
    from scripts.db_connector import DataConnector, load_db_config
    
    # 读取数据库默认配置（如存在）
    _db_cfg = load_db_config().copy() if callable(load_db_config) else {}

    def load_data(
        source: str,
        source_type: str = "file",
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "",
    ) -> Dict:
        connector = DataConnector()
        if source_type in ["mysql", "postgresql"]:
            # 应用配置文件中的默认值（如果未显式传入）
            cfg_key = source_type
            defaults = _db_cfg.get(cfg_key, {}) if isinstance(_db_cfg, dict) else {}
            db_host = host or defaults.get("host", "localhost")
            db_port = port or defaults.get("port", 3306 if source_type=="mysql" else 5432)
            db_user = user or defaults.get("user", "root" if source_type=="mysql" else "postgres")
            db_password = password if password != "" else defaults.get("password", "")
            db_database = database or defaults.get("database", "")

            connector.connect_database(
                source_type,
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_database,
            )
        elif source_type in ["influxdb", "mongodb"]:
            raise ValueError("load_data 当前仅演示支持 file/mysql/postgresql；influxdb/mongodb 请使用专用连接参数扩展")

        data = connector.load(source, source_type)
        connector.disconnect()
        return {"rows": len(data), "columns": list(data.columns)}
    
    registry.register(SkillDefinition(
        name="load_data",
        description="从文件或数据库加载数据",
        category=SkillCategory.DATA_CONNECTION,
        version="1.0.0",
        parameters=[
            SkillParameter("source", "string", "数据源路径或查询"),
            SkillParameter("source_type", "string", "数据源类型", required=False, 
                          default="file", enum=["file", "mysql", "postgresql", "influxdb", "mongodb"]),
            SkillParameter("host", "string", "数据库主机（mysql/postgresql）", required=False, default="localhost"),
            SkillParameter("port", "integer", "数据库端口（mysql默认3306，postgresql默认5432）", required=False, default=3306),
            SkillParameter("user", "string", "数据库用户名（mysql/postgresql）", required=False, default="root"),
            SkillParameter("password", "string", "数据库密码（mysql/postgresql）", required=False, default=""),
            SkillParameter("database", "string", "数据库名（mysql/postgresql）", required=False, default=""),
        ],
        returns={"rows": "行数", "columns": "列名列表"},
        func=load_data
    ))
    
    # 特征选择技能
    from scripts.feature_selector import FeatureSelector
    
    def select_features(data_path: str, target: str, method: str = "tree", top_k: int = 10, output_dir: str = "outputs", model_name: str = "") -> Dict:
        selector = FeatureSelector()
        selector.load_data(data_path, target_col=target)
        selected = selector.auto_select(method=method, top_k=top_k)
        # 保存报告到指定目录
        final_output_dir = os.path.join(output_dir, model_name) if model_name else output_dir
        os.makedirs(final_output_dir, exist_ok=True)
        report_file = os.path.join(final_output_dir, "feature_selection_report.json")
        feature_report = selector.get_report()
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(feature_report, f, ensure_ascii=False, indent=2, default=str)
        return {"selected_features": selected, "count": len(selected), "output_file": report_file}

    registry.register(SkillDefinition(
        name="select_features",
        description="自动特征选择",
        category=SkillCategory.FEATURE_ENGINEERING,
        version="1.0.0",
        parameters=[
            SkillParameter("data_path", "string", "数据文件路径"),
            SkillParameter("target", "string", "目标变量列名"),
            SkillParameter("method", "string", "选择方法", required=False, 
                          default="tree", enum=["correlation", "mutual_info", "tree"]),
            SkillParameter("top_k", "integer", "选择前K个特征", required=False, default=10),
            SkillParameter("output_dir", "string", "输出目录", required=False, default="outputs"),
            SkillParameter("model_name", "string", "模型名称（用于隔离输出目录）", required=False, default="")
        ],
        returns={"selected_features": "选中的特征列表", "count": "特征数量", "output_file": "输出文件路径"},
        func=select_features
    ))
    
    # 模型训练技能
    from scripts.auto_trainer import AutoTrainer
    
    def train_model(data_path: str, target: str, task: str = "auto", output_dir: str = "outputs", model_name: str = "") -> Dict:
        trainer = AutoTrainer(task=task)
        trainer.load_data(data_path, target_col=target)
        trainer.train_all()
        best_name, _ = trainer.select_best()
        report = trainer.get_report()
        # 保存报告到指定目录
        final_output_dir = os.path.join(output_dir, model_name) if model_name else output_dir
        os.makedirs(final_output_dir, exist_ok=True)
        report_file = os.path.join(final_output_dir, "model_training_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        return {"best_model": best_name, "report": report, "output_file": report_file}

    registry.register(SkillDefinition(
        name="train_model",
        description="自动训练多个模型并选择最优",
        category=SkillCategory.MODEL_TRAINING,
        version="1.0.0",
        parameters=[
            SkillParameter("data_path", "string", "数据文件路径"),
            SkillParameter("target", "string", "目标变量列名"),
            SkillParameter("task", "string", "任务类型", required=False,
                          default="auto", enum=["auto", "classification", "regression"]),
            SkillParameter("output_dir", "string", "输出目录", required=False, default="outputs"),
            SkillParameter("model_name", "string", "模型名称（用于隔离输出目录）", required=False, default="")
        ],
        returns={"best_model": "最优模型名称", "report": "训练报告", "output_file": "输出文件路径"},
        func=train_model
    ))
    
    # 异常检测技能
    from scripts.fault_diagnosis import FaultDiagnosisAnalyzer
    
    def detect_anomalies(data_path: str, method: str = "isolation_forest", output_dir: str = "outputs", model_name: str = "") -> Dict:
        analyzer = FaultDiagnosisAnalyzer()
        analyzer.load_data(data_path)
        result = analyzer.detect_anomalies(method=method)
        # 保存报告到指定目录
        final_output_dir = os.path.join(output_dir, model_name) if model_name else output_dir
        os.makedirs(final_output_dir, exist_ok=True)
        report_file = os.path.join(final_output_dir, "anomaly_detection_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        result["output_file"] = report_file
        return result

    registry.register(SkillDefinition(
        name="detect_anomalies",
        description="异常检测",
        category=SkillCategory.DIAGNOSIS,
        version="1.0.0",
        parameters=[
            SkillParameter("data_path", "string", "数据文件路径"),
            SkillParameter("method", "string", "检测方法", required=False,
                          default="isolation_forest", enum=["isolation_forest", "lof", "dbscan", "zscore"]),
            SkillParameter("output_dir", "string", "输出目录", required=False, default="outputs"),
            SkillParameter("model_name", "string", "模型名称（用于隔离输出目录）", required=False, default="")
        ],
        returns={"anomaly_count": "异常数量", "anomaly_rate": "异常率", "output_file": "输出文件路径"},
        func=detect_anomalies
    ))
    
    print(f"已注册 {len(registry.skills)} 个工业分析技能")
    return registry


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="技能注册中心")
    parser.add_argument("--list", action="store_true", help="列出所有技能")
    parser.add_argument("--category", help="按类别筛选")
    parser.add_argument("--search", help="搜索技能")
    parser.add_argument("--export", help="导出技能注册表")
    parser.add_argument("--register-all", action="store_true", help="注册所有工业技能")
    
    args = parser.parse_args()
    
    registry = get_registry()
    
    if args.register_all:
        register_industrial_skills()
    
    if args.list or args.category or args.search:
        category = None
        if args.category:
            category = SkillCategory(args.category)
        
        skills = registry.find(query=args.search or "", category=category)
        
        print(f"\n找到 {len(skills)} 个技能:")
        for skill in skills:
            print(f"  - {skill.name} [{skill.category.value}]: {skill.description[:50]}...")
    
    if args.export:
        registry.export(args.export)
        print(f"已导出到: {args.export}")
    
    print(f"\n统计: {json.dumps(registry.get_statistics(), indent=2)}")


if __name__ == "__main__":
    main()

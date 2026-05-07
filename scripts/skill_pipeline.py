#!/usr/bin/env python3
"""
技能组合编排器
支持技能串联、并联、条件分支和循环执行
"""

import os
import json
import copy
import traceback
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed


class StepType(Enum):
    """步骤类型"""
    SKILL = "skill"           # 单个技能调用
    SEQUENCE = "sequence"     # 串联执行
    PARALLEL = "parallel"     # 并联执行
    CONDITION = "condition"   # 条件分支
    LOOP = "loop"             # 循环执行
    TRANSFORM = "transform"   # 数据转换


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStep:
    """流水线步骤"""
    
    def __init__(self, name: str, step_type: StepType, config: Dict[str, Any]):
        self.name = name
        self.step_type = step_type
        self.config = config
        self.status = StepStatus.PENDING
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        self.children: List['PipelineStep'] = []
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.step_type.value,
            "status": self.status.value,
            "config": self.config,
            "result": self.result,
            "error": self.error,
            "duration_ms": self._get_duration(),
            "children": [c.to_dict() for c in self.children]
        }
    
    def _get_duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None


class SkillPipeline:
    """技能流水线"""
    
    def __init__(self, name: str, registry=None):
        self.name = name
        self.registry = registry
        self.steps: List[PipelineStep] = []
        self.context: Dict[str, Any] = {}
        self.execution_history: List[Dict] = []
        self.max_workers = 4
    
    def add_skill(self, name: str, skill_name: str, 
                  params: Optional[Dict] = None,
                  input_mapping: Optional[Dict] = None,
                  output_key: Optional[str] = None) -> 'SkillPipeline':
        """添加技能步骤"""
        step = PipelineStep(name, StepType.SKILL, {
            "skill_name": skill_name,
            "params": params or {},
            "input_mapping": input_mapping or {},
            "output_key": output_key or name
        })
        self.steps.append(step)
        return self
    
    def add_sequence(self, name: str, steps: List[PipelineStep]) -> 'SkillPipeline':
        """添加串联步骤"""
        step = PipelineStep(name, StepType.SEQUENCE, {})
        step.children = steps
        self.steps.append(step)
        return self
    
    def add_parallel(self, name: str, steps: List[PipelineStep]) -> 'SkillPipeline':
        """添加并联步骤"""
        step = PipelineStep(name, StepType.PARALLEL, {})
        step.children = steps
        self.steps.append(step)
        return self
    
    def add_condition(self, name: str, condition: Callable[[Dict], bool],
                      if_true: PipelineStep, if_false: Optional[PipelineStep] = None) -> 'SkillPipeline':
        """添加条件分支"""
        step = PipelineStep(name, StepType.CONDITION, {
            "condition": condition
        })
        step.children = [if_true]
        if if_false:
            step.children.append(if_false)
        self.steps.append(step)
        return self
    
    def add_loop(self, name: str, items_key: str, 
                 body: PipelineStep, max_iterations: int = 100) -> 'SkillPipeline':
        """添加循环步骤"""
        step = PipelineStep(name, StepType.LOOP, {
            "items_key": items_key,
            "max_iterations": max_iterations
        })
        step.children = [body]
        self.steps.append(step)
        return self
    
    def add_transform(self, name: str, transform_func: Callable[[Dict], Dict],
                      output_key: str) -> 'SkillPipeline':
        """添加数据转换步骤"""
        step = PipelineStep(name, StepType.TRANSFORM, {
            "transform_func": transform_func,
            "output_key": output_key
        })
        self.steps.append(step)
        return self
    
    def _execute_skill(self, step: PipelineStep) -> Any:
        """执行技能步骤"""
        config = step.config
        skill_name = config["skill_name"]
        params = copy.deepcopy(config["params"])
        
        # 应用输入映射
        for param_name, context_key in config.get("input_mapping", {}).items():
            if context_key in self.context:
                params[param_name] = self.context[context_key]
        
        # 调用技能
        if self.registry:
            result = self.registry.call(skill_name, **params)
        else:
            raise ValueError(f"未配置技能注册中心，无法调用技能: {skill_name}")
        
        # 存储输出
        output_key = config.get("output_key", step.name)
        self.context[output_key] = result
        
        return result
    
    def _execute_sequence(self, step: PipelineStep) -> List[Any]:
        """执行串联步骤"""
        results = []
        for child in step.children:
            result = self._execute_step(child)
            results.append(result)
        return results
    
    def _execute_parallel(self, step: PipelineStep) -> List[Any]:
        """执行并联步骤"""
        results = [None] * len(step.children)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(self._execute_step, child): i
                for i, child in enumerate(step.children)
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {"error": str(e)}
        
        return results
    
    def _execute_condition(self, step: PipelineStep) -> Any:
        """执行条件分支"""
        condition_func = step.config["condition"]
        
        if condition_func(self.context):
            return self._execute_step(step.children[0])
        elif len(step.children) > 1:
            return self._execute_step(step.children[1])
        else:
            step.status = StepStatus.SKIPPED
            return None
    
    def _execute_loop(self, step: PipelineStep) -> List[Any]:
        """执行循环步骤"""
        items_key = step.config["items_key"]
        max_iterations = step.config["max_iterations"]
        
        items = self.context.get(items_key, [])
        if not isinstance(items, list):
            items = [items]
        
        results = []
        for i, item in enumerate(items[:max_iterations]):
            self.context["_loop_index"] = i
            self.context["_loop_item"] = item
            
            result = self._execute_step(step.children[0])
            results.append(result)
        
        return results
    
    def _execute_transform(self, step: PipelineStep) -> Any:
        """执行数据转换"""
        transform_func = step.config["transform_func"]
        output_key = step.config["output_key"]
        
        result = transform_func(self.context)
        self.context[output_key] = result
        
        return result
    
    def _execute_step(self, step: PipelineStep) -> Any:
        """执行单个步骤"""
        step.status = StepStatus.RUNNING
        step.start_time = datetime.now()
        
        try:
            if step.step_type == StepType.SKILL:
                result = self._execute_skill(step)
            elif step.step_type == StepType.SEQUENCE:
                result = self._execute_sequence(step)
            elif step.step_type == StepType.PARALLEL:
                result = self._execute_parallel(step)
            elif step.step_type == StepType.CONDITION:
                result = self._execute_condition(step)
            elif step.step_type == StepType.LOOP:
                result = self._execute_loop(step)
            elif step.step_type == StepType.TRANSFORM:
                result = self._execute_transform(step)
            else:
                raise ValueError(f"未知步骤类型: {step.step_type}")
            
            step.status = StepStatus.COMPLETED
            step.result = result
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            raise
        
        finally:
            step.end_time = datetime.now()
        
        return result
    
    def run(self, initial_context: Optional[Dict] = None) -> Dict[str, Any]:
        """运行流水线"""
        self.context = initial_context or {}
        
        execution_record = {
            "pipeline": self.name,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "status": "running",
            "steps_completed": 0,
            "steps_failed": 0,
            "results": {}
        }
        
        print(f"\n{'='*60}")
        print(f"运行流水线: {self.name}")
        print(f"{'='*60}")
        
        try:
            for i, step in enumerate(self.steps):
                print(f"\n[{i+1}/{len(self.steps)}] 执行: {step.name} ({step.step_type.value})")
                
                self._execute_step(step)
                execution_record["steps_completed"] += 1
                
                print(f"    状态: {step.status.value}")
                if step.result:
                    print(f"    结果: {str(step.result)[:100]}...")
            
            execution_record["status"] = "completed"
            
        except Exception as e:
            execution_record["status"] = "failed"
            execution_record["error"] = str(e)
            execution_record["steps_failed"] += 1
            print(f"    错误: {e}")
        
        finally:
            execution_record["end_time"] = datetime.now().isoformat()
            execution_record["results"] = self.context
            self.execution_history.append(execution_record)
        
        print(f"\n{'='*60}")
        print(f"流水线完成: {execution_record['status']}")
        print(f"{'='*60}")
        
        return {
            "status": execution_record["status"],
            "context": self.context,
            "steps": [s.to_dict() for s in self.steps]
        }
    
    def to_dict(self) -> Dict:
        """导出流水线定义"""
        return {
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps]
        }
    
    def save(self, path: str):
        """保存流水线定义"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)


class PipelineBuilder:
    """流水线构建器（链式 API）"""
    
    def __init__(self, name: str, registry=None):
        self.pipeline = SkillPipeline(name, registry)
    
    def skill(self, name: str, skill_name: str, **kwargs) -> 'PipelineBuilder':
        self.pipeline.add_skill(name, skill_name, **kwargs)
        return self
    
    def transform(self, name: str, func: Callable, output_key: str) -> 'PipelineBuilder':
        self.pipeline.add_transform(name, func, output_key)
        return self
    
    def condition(self, name: str, cond: Callable, if_true: PipelineStep, 
                  if_false: Optional[PipelineStep] = None) -> 'PipelineBuilder':
        self.pipeline.add_condition(name, cond, if_true, if_false)
        return self
    
    def build(self) -> SkillPipeline:
        return self.pipeline


def create_industrial_pipeline(registry, output_dir: str = "outputs",
                               model_name: str = "") -> SkillPipeline:
    """创建工业数据分析流水线示例

    Args:
        registry: 技能注册中心
        output_dir: 输出目录（默认 outputs）
        model_name: 模型名称（用于隔离输出，如 glm5.1/kimi-2.6/deepseek-v4）
    """
    pipeline = SkillPipeline("industrial_analysis", registry)

    # 共享参数（用于模型隔离输出）
    shared_params = {
        "output_dir": output_dir,
        "model_name": model_name
    }

    # 1. 加载数据（不需要输出目录）
    pipeline.add_skill(
        name="load",
        skill_name="load_data",
        params={"source_type": "file"},
        input_mapping={"source": "data_path"},
        output_key="raw_data"
    )

    # 2. 特征选择（支持模型隔离输出）
    pipeline.add_skill(
        name="feature_select",
        skill_name="select_features",
        params=shared_params.copy(),
        input_mapping={"data_path": "data_path", "target": "target_col"},
        output_key="selected_features"
    )

    # 3. 模型训练（支持模型隔离输出）
    pipeline.add_skill(
        name="train",
        skill_name="train_model",
        params=shared_params.copy(),
        input_mapping={"data_path": "data_path", "target": "target_col"},
        output_key="model_result"
    )

    # 4. 异常检测（支持模型隔离输出）
    pipeline.add_skill(
        name="anomaly",
        skill_name="detect_anomalies",
        params=shared_params.copy(),
        input_mapping={"data_path": "data_path"},
        output_key="anomaly_result"
    )

    return pipeline


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="技能流水线")
    parser.add_argument("--demo", action="store_true", help="运行演示")
    
    args = parser.parse_args()
    
    if args.demo:
        # 演示简单流水线
        pipeline = SkillPipeline("demo_pipeline")
        
        # 添加转换步骤（不需要注册中心）
        pipeline.add_transform(
            name="init",
            transform_func=lambda ctx: {"message": "Hello, Pipeline!"},
            output_key="greeting"
        )
        
        pipeline.add_transform(
            name="process",
            transform_func=lambda ctx: {"processed": ctx.get("greeting", {}).get("message", "").upper()},
            output_key="result"
        )
        
        result = pipeline.run({"input": "test"})
        print(f"\n最终结果: {json.dumps(result, ensure_ascii=False, indent=2, default=str)}")


if __name__ == "__main__":
    main()

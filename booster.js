/* Native XGBoost JSON inference: scalar numeric gbtree / squared-error only. */
(function(root) {
  class TreeBooster {
    constructor(document, columns) {
      const l=document.learner;
      if (!l || l.gradient_booster?.name!=='gbtree' || l.objective?.name!=='reg:squarederror')
        throw Error('수치형 gbtree / reg:squarederror XGBoost JSON 모델만 지원합니다.');
      const p=l.learner_model_param;
      this.n=Number(p.num_feature);
      if(Number(p.num_class)!==0 || Number(p.num_target??1)!==1 || this.n!==columns.length)
        throw Error('단일 수요 출력과 feature 개수를 확인하세요.');
      if(l.feature_names?.length && JSON.stringify(l.feature_names)!==JSON.stringify(columns))
        throw Error('model.json과 config.json의 feature 순서가 다릅니다.');
      if(l.feature_types?.some(t=>t==='c')) throw Error('범주형 분할 모델은 지원하지 않습니다.');
      let base=JSON.parse(p.base_score); if(Array.isArray(base)){if(base.length!==1)throw Error('다중 출력은 지원하지 않습니다.');base=base[0];}
      this.base=Math.fround(Number(base));
      if(!Number.isFinite(this.base))throw Error('모델 base_score가 잘못되었습니다.');
      const model=l.gradient_booster.model;
      if(!model.trees?.length || model.tree_info?.some(n=>n!==0))throw Error('모델 트리 구성이 잘못되었습니다.');
      this.trees=model.trees.map(t=>{
        const count=Number(t.tree_param.num_nodes);
        if(Number(t.tree_param.size_leaf_vector??1)>1 || t.split_type?.some(n=>n!==0))throw Error('지원하지 않는 트리 형식입니다.');
        const arrays=['left_children','right_children','split_indices','split_conditions','default_left'];
        if(!Number.isInteger(count)||count<1||arrays.some(k=>t[k]?.length!==count))throw Error('트리 노드 배열이 손상되었습니다.');
        const visited=new Set(), stack=[0];
        while(stack.length){const i=stack.pop();if(!Number.isInteger(i)||i<0||i>=count||visited.has(i))throw Error('트리 연결이 잘못되었습니다.');visited.add(i);
          if(!Number.isFinite(t.split_conditions[i]))throw Error('트리 값이 유효하지 않습니다.');
          if(t.left_children[i]===-1){if(t.right_children[i]!==-1)throw Error('leaf 연결 오류');}
          else {if(!Number.isInteger(t.split_indices[i])||t.split_indices[i]<0||t.split_indices[i]>=this.n)throw Error('feature 인덱스 오류');stack.push(t.left_children[i],t.right_children[i]);}
        }
        if(visited.size!==count)throw Error('연결되지 않은 트리 노드가 있습니다.');
        return {left:Int32Array.from(t.left_children),right:Int32Array.from(t.right_children),feature:Int32Array.from(t.split_indices),value:Float32Array.from(t.split_conditions),missing:Uint8Array.from(t.default_left)};
      });
    }
    predict(rows) {
      return rows.map(row=>{
        if(row.length!==this.n)throw Error('예측 feature 개수가 다릅니다.');
        const x=row.map(v=>v==null?NaN:Math.fround(v));let sum=this.base;
        for(const t of this.trees){let i=0;while(t.left[i]!==-1){const v=x[t.feature[i]];i=Number.isNaN(v)?(t.missing[i]?t.left[i]:t.right[i]):(v<t.value[i]?t.left[i]:t.right[i]);}sum=Math.fround(sum+t.value[i]);}
        return sum;
      });
    }
  }
  root.TreeBooster=TreeBooster;
  if(typeof module!=='undefined')module.exports={TreeBooster};
})(globalThis);

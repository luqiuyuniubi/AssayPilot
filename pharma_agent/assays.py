"""Explicit assay semantics. No model guesses direction, controls or units."""
PROFILES={
 'inhibition':{'label':'报告基因/功能阻断','direction':'decreasing','potency_label':'IC50','potency_field':'ic50_nm','effect_label':'抑制率','principle':'按高、低信号对照归一化，评价随浓度增加的功能性抑制。'},
 'activation':{'label':'受体激动/信号激活','direction':'increasing','potency_label':'EC50','potency_field':'ec50_nm','effect_label':'激活率','principle':'按低信号基础对照与高信号最大响应对照归一化，评价随浓度增加的激活响应。'},
 'viability':{'label':'细胞活力/细胞毒性','direction':'decreasing','potency_label':'CC50','potency_field':'cc50_nm','effect_label':'活力下降率','principle':'把原始活力读数下降作为效应；CC50为拟合上下平台中点，不等于已证实细胞死亡率或绝对50%活力下降。'},
 'enzyme':{'label':'酶活性抑制','direction':'decreasing','potency_label':'IC50','potency_field':'ic50_nm','effect_label':'酶抑制率','principle':'分析酶活性随浓度下降的终点读数；不把IC50解释为Ki，不分析反应速率或机制。'},
}
def profile(options=None):
    name=(options or {}).get('assay_type','inhibition')
    if name not in PROFILES:raise ValueError('请选择有效分析场景。')
    p={'type':name,**PROFILES[name]}
    p['readout']=str((options or {}).get('readout','RLU'))[:40]
    p['endpoint_unit']='nM';return p
def potency(sample):return sample.get('potency_nm',sample.get('ic50_nm'))
def effect(value,high,low,assay):
    return 100*(value-low)/(high-low) if assay['direction']=='increasing' else 100*(high-value)/(high-low)

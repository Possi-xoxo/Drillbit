"""Deterministic perceptual-error-driven construction of a constrained DMC palette."""
from collections import defaultdict, deque
from dataclasses import dataclass
import logging
import math

import numpy as np
from PIL import Image
from .models import DitherMode
from .palette_system import rgb_to_lab
from .logging_manager import log_timing

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class FidelityTuning:
    source_channel_bits: int = 4
    dmc_candidates_per_cluster: int = 10
    dominance_exponent: float = 0.72
    minimum_relative_error_reduction: float = 0.00001
    minimum_mean_delta_e_reduction: float = 0.0001
    low_color_minimum_coverage: float = 0.025
    low_color_explained_coverage: float = 0.95


BALANCED_FIDELITY = FidelityTuning()


def component_metrics(label_grid):
    """Exact four-connected metrics, excluding transparent label -1."""
    height,width=label_grid.shape;labels=label_grid.ravel().tolist();seen=bytearray(len(labels));sizes=defaultdict(list)
    for start,label in enumerate(labels):
        if seen[start] or label<0:continue
        seen[start]=1;queue=deque([start]);size=0
        while queue:
            current=queue.popleft();size+=1;x=current%width;y=current//width
            for other in (current-1 if x else -1,current+1 if x+1<width else -1,current-width if y else -1,current+width if y+1<height else -1):
                if other>=0 and not seen[other] and labels[other]==label:seen[other]=1;queue.append(other)
        sizes[label].append(size)
    return {label:{"components":len(parts),"single_cells":sum(size==1 for size in parts),
                   "two_cell_components":sum(size==2 for size in parts),"three_cell_components":sum(size==3 for size in parts),
                   "tiny_cells":sum(size for size in parts if size<=3),"largest_region":max(parts)} for label,parts in sizes.items()}


def _palette_arrays(palette):
    codes=[color.code for color in palette.colors]
    return codes,np.asarray([palette._labs[code] for code in codes],dtype=np.float32)


def analyze_source_colors(logical_image,target,dither_mode,opaque_mask=None,tuning=BALANCED_FIDELITY):
    """Quantize opaque logical cells into a rich weighted source representation."""
    rgb=np.asarray(logical_image.convert("RGB"),dtype=np.uint8)
    opaque=np.ones(rgb.shape[:2],dtype=bool) if opaque_mask is None else np.asarray(opaque_mask,dtype=np.uint8)>=128
    pixels=rgb[opaque]
    if not len(pixels):return np.full(opaque.shape,-1,dtype=np.int16),np.empty((0,3),dtype=np.float32),np.empty(0,dtype=np.int64),[]
    shift=8-tuning.source_channel_bits;bins=(pixels>>shift).astype(np.int32);keys=(bins[:,0]<<(2*tuning.source_channel_bits))|(bins[:,1]<<tuning.source_channel_bits)|bins[:,2]
    _unique,inverse,counts=np.unique(keys,return_inverse=True,return_counts=True);labels=np.full(opaque.shape,-1,dtype=np.int32);labels[opaque]=inverse
    sums=np.stack([np.bincount(inverse,weights=pixels[:,channel],minlength=len(counts)) for channel in range(3)],axis=1)
    averaged=np.rint(sums/counts[:,None]).clip(0,255).astype(np.uint8);rgbs=[tuple(int(value) for value in row) for row in averaged]
    labs=np.asarray([rgb_to_lab(rgb_value) for rgb_value in rgbs],dtype=np.float32)
    return labels,labs,counts.astype(np.int64),rgbs


def generate_dmc_candidates(source_labs,palette,tuning=BALANCED_FIDELITY):
    """Union several plausible DMC matches for every source cluster."""
    codes,dmc_labs=_palette_arrays(palette)
    if not len(source_labs):return [],np.empty((0,0),dtype=np.float32)
    all_distances=np.sqrt(np.sum((source_labs[:,None,:]-dmc_labs[None,:,:])**2,axis=2))
    nearest=np.argsort(all_distances,axis=1,kind="stable")[:,:tuning.dmc_candidates_per_cluster]
    indices=sorted(set(int(value) for value in nearest.ravel()))
    return [codes[index] for index in indices],all_distances[:,indices]


def grow_palette(source_distances,counts,candidate_codes,target,tuning=BALANCED_FIDELITY):
    """Add the DMC color with the largest balanced residual-error reduction."""
    if not len(counts):return [],[]
    weights=np.power(counts.astype(np.float64),tuning.dominance_exponent);actual_weights=counts.astype(np.float64)
    selected=[];growth=[];best=np.full(len(counts),np.inf,dtype=np.float64);remaining=np.ones(len(candidate_codes),dtype=bool);attempts=0
    while len(selected)<target and np.any(remaining):
        attempts+=1
        options=np.flatnonzero(remaining);proposed=np.minimum(best[:,None],source_distances[:,options])
        errors=np.sum(proposed*weights[:,None],axis=0);position=int(np.argmin(errors));choice=int(options[position]);new_best=proposed[:,position]
        old_error=float(np.sum(best*weights)) if np.isfinite(best).all() else math.inf;new_error=float(errors[position])
        gain=old_error-new_error if math.isfinite(old_error) else math.inf;relative=gain/old_error if math.isfinite(old_error) and old_error>0 else math.inf
        mean_gain=float(np.sum((best-new_best)*actual_weights)/actual_weights.sum()) if math.isfinite(old_error) else math.inf
        if selected and relative<tuning.minimum_relative_error_reduction and mean_gain<tuning.minimum_mean_delta_e_reduction:break
        best=new_best;remaining[choice]=False;selected.append(choice)
        assignment=np.argmin(source_distances[:,selected],axis=1);used_positions=set(int(value) for value in assignment)
        if len(used_positions)<len(selected):
            selected=[value for position,value in enumerate(selected) if position in used_positions]
            best=np.min(source_distances[:,selected],axis=1)
        growth.append({"slot":len(selected),"code":candidate_codes[choice],"weighted_error":float(np.sum(best*weights)),
                       "relative_reduction":None if not math.isfinite(relative) else relative,
                       "mean_delta_e_reduction":None if not math.isfinite(mean_gain) else mean_gain})
    return selected,growth


def fidelity_metrics(cluster_errors,counts):
    if not len(counts):return {"mean_delta_e":0.0,"median_delta_e":0.0,"p90_delta_e":0.0,"p99_delta_e":0.0}
    order=np.argsort(cluster_errors,kind="stable");values=cluster_errors[order];weights=counts[order];cumulative=np.cumsum(weights);total=int(cumulative[-1])
    percentile=lambda q:float(values[min(len(values)-1,np.searchsorted(cumulative,total*q,side="left"))])
    return {"mean_delta_e":float(np.average(cluster_errors,weights=counts)),"median_delta_e":percentile(.5),"p90_delta_e":percentile(.9),"p99_delta_e":percentile(.99)}


def analyze_confetti(final_labels,selected_codes):
    """Measure fragmentation after assignment without changing the pattern."""
    metrics=component_metrics(final_labels);per_color={};singles=tiny=0
    for index,code in enumerate(selected_codes):
        metric=metrics.get(index,{"components":0,"single_cells":0,"two_cell_components":0,"three_cell_components":0,"tiny_cells":0,"largest_region":0})
        cells=int(np.count_nonzero(final_labels==index));singles+=metric["single_cells"];tiny+=metric["tiny_cells"]
        per_color[code]={**metric,"cells":cells,"tiny_cell_percentage":metric["tiny_cells"]/cells if cells else 0.0}
    return {"single_cell_components":singles,"tiny_component_cells":tiny,"per_color":per_color}


def optimize_palette(logical_image,target,palette,dither_mode=DitherMode.OFF,tuning=BALANCED_FIDELITY,opaque_mask=None):
    with log_timing("source color analysis",LOG):labels,source_labs,counts,_rgbs=analyze_source_colors(logical_image,target,dither_mode,opaque_mask,tuning)
    if not len(counts):
        return [None]*labels.size,{"requested_colors":target,"colors_used":0,"selected_codes":[],"utilization_reason":"The pattern contains no opaque drill cells.","candidate_count":0,"growth":[],**fidelity_metrics([],[]),"confetti":analyze_confetti(labels,[])}
    with log_timing("DMC candidate generation",LOG):candidate_codes,distances=generate_dmc_candidates(source_labs,palette,tuning)
    LOG.info("LAB distance workspace source_colors=%s candidates=%s shape=%sx%s dtype=%s estimated_bytes=%s",len(source_labs),len(candidate_codes),*distances.shape,distances.dtype,distances.nbytes)
    substantial=counts/counts.sum()>=tuning.low_color_minimum_coverage
    substantial_count=int(np.count_nonzero(substantial));explained=float(counts[substantial].sum()/counts.sum())
    effective_target=substantial_count if substantial_count<=2 and explained>=tuning.low_color_explained_coverage else target
    with log_timing("residual-error palette growth",LOG):selected_indices,growth=grow_palette(distances,counts,candidate_codes,effective_target,tuning)
    selected_codes=[candidate_codes[index] for index in selected_indices]
    selected_distances=distances[:,selected_indices];cluster_assignment=np.argmin(selected_distances,axis=1);cluster_errors=np.min(selected_distances,axis=1)
    opaque=labels>=0
    if dither_mode==DitherMode.FLOYD_STEINBERG:
        palette_image=Image.new("P",(1,1));palette_data=[]
        for code in selected_codes:palette_data.extend(palette.by_code[code].rgb)
        palette_data.extend(list(palette.by_code[selected_codes[0]].rgb)*(256-len(selected_codes)));palette_image.putpalette(palette_data)
        final_labels=np.asarray(logical_image.convert("RGB").quantize(palette=palette_image,dither=Image.Dither.FLOYDSTEINBERG),dtype=np.int16).copy()
        final_labels[~opaque]=-1
    else:
        final_labels=np.full(labels.shape,-1,dtype=np.int16);final_labels[opaque]=cluster_assignment[labels[opaque]]
    ids=[None if label<0 else selected_codes[int(label)] for label in final_labels.ravel()];used_set={code for code in ids if code is not None};used_codes=[code for code in selected_codes if code in used_set]
    metrics=fidelity_metrics(cluster_errors,counts);first_index=candidate_codes.index(growth[0]["code"]);initial=fidelity_metrics(distances[:,first_index],counts)
    with log_timing("confetti analysis",LOG):confetti=analyze_confetti(final_labels,selected_codes)
    reason=f"{target-len(used_codes)} additional colors produced negligible perceptual improvement." if len(used_codes)<target else ""
    LOG.debug("Requested colors: %d; candidate DMC colors: %d",target,len(candidate_codes))
    for item in growth:LOG.debug("Selected #%d DMC %s; error reduction %s",item["slot"],item["code"],"initial" if item["relative_reduction"] is None else f'{item["relative_reduction"]:.3%}')
    LOG.debug("Final mean DeltaE %.3f; p90 DeltaE %.3f; single-cell components %d",metrics["mean_delta_e"],metrics["p90_delta_e"],confetti["single_cell_components"])
    return ids,{"requested_colors":target,"colors_used":len(used_codes),"selected_codes":used_codes,"utilization_reason":reason,
                "candidate_count":len(candidate_codes),"source_cluster_count":len(counts),"growth":growth,
                "initial_mean_delta_e":initial["mean_delta_e"],"initial_p90_delta_e":initial["p90_delta_e"],**metrics,"confetti":confetti,
                "candidates":[{"index":i,"coverage":int(count)/int(counts.sum())} for i,count in enumerate(counts)]}

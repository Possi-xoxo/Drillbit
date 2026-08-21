"""Deterministic, drill-grid-aware construction of a constrained reference palette."""
from collections import defaultdict, deque
from dataclasses import dataclass
import logging
import math

import numpy as np
from PIL import Image

from .models import DitherMode
from .palette_system import rgb_to_lab

LOG = logging.getLogger(__name__)

@dataclass(frozen=True)
class OptimizationTuning:
    """Centralized Balanced-mode weights and safety thresholds."""
    candidate_multiplier: int = 3
    max_candidates: int = 64
    dmc_alternatives: int = 18
    minimum_relative_coverage: float = 0.015
    minimum_cells: int = 4
    detail_minimum_cells: int = 2
    detail_maximum_sqrt_scale: float = 0.35
    detail_contrast_delta_e: float = 28.0
    alternative_delta_e_slack: float = 12.0
    maximum_alternative_delta_e: float = 35.0
    minimum_dmc_separation: float = 5.0
    coverage_weight: float = 3.0
    coherence_weight: float = 1.35
    detail_weight: float = 0.85
    distinctiveness_weight: float = 1.1
    confetti_weight: float = 1.6
    redundancy_weight: float = 1.0
    minimum_utility: float = 0.20

BALANCED_TUNING = OptimizationTuning()

@dataclass
class Candidate:
    index: int
    rgb: tuple[int, int, int]
    lab: tuple[float, float, float]
    count: int
    coverage: float
    components: int
    single_cells: int
    tiny_cells: int
    largest_region: int
    coherence: float
    confetti_ratio: float
    contrast: float
    base_utility: float

def delta_e(left, right):
    return math.sqrt(sum((a-b)**2 for a,b in zip(left,right)))

def component_metrics(label_grid):
    """Return exact four-connected component statistics for every label in one O(n) pass."""
    height,width=label_grid.shape;labels=label_grid.ravel().tolist();seen=bytearray(len(labels));sizes=defaultdict(list)
    for start,label in enumerate(labels):
        if seen[start]:continue
        seen[start]=1;queue=deque([start]);size=0
        while queue:
            current=queue.popleft();size+=1;x=current%width;y=current//width
            for other in (current-1 if x else -1,current+1 if x+1<width else -1,current-width if y else -1,current+width if y+1<height else -1):
                if other>=0 and not seen[other] and labels[other]==label:seen[other]=1;queue.append(other)
        sizes[label].append(size)
    return {label:{"components":len(parts),"single_cells":sum(size==1 for size in parts),"tiny_cells":sum(size for size in parts if size<=3),
                   "largest_region":max(parts),"average_region":sum(parts)/len(parts)} for label,parts in sizes.items()}

def _candidate_contrasts(labels, labs):
    neighbors=defaultdict(list)
    for first,second in ((labels[:,:-1],labels[:,1:]),(labels[:-1,:],labels[1:,:])):
        pairs=np.stack((first.ravel(),second.ravel()),axis=1);pairs=pairs[(pairs[:,0]!=pairs[:,1])&(pairs[:,0]>=0)&(pairs[:,1]>=0)]
        if len(pairs):
            for a,b in np.unique(np.sort(pairs,axis=1),axis=0):
                distance=delta_e(labs[int(a)],labs[int(b)]);neighbors[int(a)].append(distance);neighbors[int(b)].append(distance)
    return {index:(sum(values)/len(values) if values else 0.0) for index,values in neighbors.items()}

def discover_candidates(logical_image, target, dither_mode, tuning=BALANCED_TUNING, opaque_mask=None):
    colors=max(2,min(tuning.max_candidates,max(target,target*tuning.candidate_multiplier)))
    dither=Image.Dither.NONE if dither_mode==DitherMode.OFF else Image.Dither.FLOYDSTEINBERG
    rgb=np.asarray(logical_image.convert("RGB"),dtype=np.uint8)
    opaque=np.ones(rgb.shape[:2],dtype=bool) if opaque_mask is None else np.asarray(opaque_mask,dtype=np.uint8)>=128
    pixels=rgb[opaque]
    if not len(pixels):return None,np.full(opaque.shape,-1,dtype=np.int16),[]
    sample=Image.fromarray(pixels.reshape(1,-1,3),"RGB")
    indexed=sample.quantize(colors=colors,method=Image.Quantize.MEDIANCUT,dither=dither)
    flat_labels=np.asarray(indexed,dtype=np.int16).ravel();labels=np.full(opaque.shape,-1,dtype=np.int16);labels[opaque]=flat_labels
    palette_data=indexed.getpalette();counts=np.bincount(flat_labels);used=np.flatnonzero(counts)
    rgbs={int(index):tuple(palette_data[int(index)*3:int(index)*3+3]) for index in used}
    labs={index:rgb_to_lab(rgb) for index,rgb in rgbs.items()};metrics=component_metrics(labels);contrasts=_candidate_contrasts(labels,labs);total=len(flat_labels);candidates=[]
    for index in used:
        index=int(index);count=int(counts[index]);coverage=count/total;metric=metrics[index];confetti=metric["tiny_cells"]/count;coherence=1-confetti
        contrast=contrasts.get(index,0.0);detail=min(1.0,contrast/50.0)
        utility=(tuning.coverage_weight*math.sqrt(coverage)+tuning.coherence_weight*coherence+tuning.detail_weight*detail-tuning.confetti_weight*confetti)
        candidates.append(Candidate(index,rgbs[index],labs[index],count,coverage,metric["components"],metric["single_cells"],metric["tiny_cells"],metric["largest_region"],coherence,confetti,contrast,utility))
    return indexed,labels,sorted(candidates,key=lambda item:(-item.base_utility,-item.count,item.index))

def _palette_arrays(palette):
    codes=[color.code for color in palette.colors];labs=np.asarray([palette._labs[code] for code in codes],dtype=np.float64);return codes,labs

def optimize_palette(logical_image,target,palette,dither_mode=DitherMode.OFF,tuning=BALANCED_TUNING,opaque_mask=None):
    """Select useful distinct DMC colors as a set and return IDs plus diagnostics."""
    indexed,labels,candidates=discover_candidates(logical_image,target,dither_mode,tuning,opaque_mask);codes,dmc_labs=_palette_arrays(palette);selected=[];candidate_to_code={};rejected=[]
    if not candidates:
        return [None]*labels.size,{"requested_colors":target,"colors_used":0,"selected_codes":[],"utilization_reason":"The pattern contains no opaque drill cells.","candidate_count":0,"candidates":[]}
    remaining=list(candidates)
    while remaining and len(selected)<target:
        best=None
        for candidate in remaining:
            opaque_count=int(np.count_nonzero(labels>=0));detail_ceiling=max(tuning.detail_minimum_cells,round(math.sqrt(opaque_count)*tuning.detail_maximum_sqrt_scale))
            meaningful=(candidate.coverage>=tuning.minimum_relative_coverage and candidate.count>=tuning.minimum_cells) or (tuning.detail_minimum_cells<=candidate.count<=detail_ceiling and candidate.contrast>=tuning.detail_contrast_delta_e)
            if not meaningful:continue
            distances=np.sqrt(np.sum((dmc_labs-np.asarray(candidate.lab))**2,axis=1));order=np.argsort(distances,kind="stable")[:tuning.dmc_alternatives];nearest=float(distances[order[0]])
            choices=[]
            for palette_index in order:
                code=codes[int(palette_index)];match=float(distances[palette_index])
                if code in selected or match>nearest+tuning.alternative_delta_e_slack or match>tuning.maximum_alternative_delta_e:continue
                separation=min((delta_e(palette._labs[code],palette._labs[other]) for other in selected),default=50.0)
                redundancy=max(0.0,(tuning.minimum_dmc_separation-separation)/tuning.minimum_dmc_separation)
                choice_cost=match+redundancy*12.0;choices.append((choice_cost,code,separation,match))
            if not choices:continue
            _cost,code,separation,match=min(choices,key=lambda item:(item[0],item[1]))
            distinct=min(1.0,separation/40.0);redundancy=max(0.0,(tuning.minimum_dmc_separation-separation)/tuning.minimum_dmc_separation)
            utility=candidate.base_utility+tuning.distinctiveness_weight*distinct-tuning.redundancy_weight*redundancy
            proposal=(utility,candidate.count,-candidate.index,candidate,code,match,separation)
            if best is None or proposal[:3]>best[:3]:best=proposal
        if best is None or best[0]<tuning.minimum_utility:break
        utility,_count,_neg_index,candidate,code,match,separation=best;selected.append(code);candidate_to_code[candidate.index]=code;remaining.remove(candidate)
        LOG.debug("Selected DMC %s candidate=%s coverage=%.2f%% separation=%.2f confetti=%.2f%% utility=%.3f",code,candidate.index,candidate.coverage*100,separation,candidate.confetti_ratio*100,utility)
    if not selected:
        candidate=candidates[0];selected=[palette.nearest(candidate.rgb).code];candidate_to_code[candidate.index]=selected[0]
    selected_labs=np.asarray([palette._labs[code] for code in selected])
    for candidate in candidates:
        if candidate.index not in candidate_to_code:
            distances=np.sqrt(np.sum((selected_labs-np.asarray(candidate.lab))**2,axis=1));candidate_to_code[candidate.index]=selected[int(np.argmin(distances))]
    ids=[None if label<0 else candidate_to_code[int(label)] for label in labels.ravel()];used_codes=sorted({code for code in ids if code is not None},key=selected.index)
    reason="" if len(used_codes)==target else f"{target-len(used_codes)} additional colors were too similar, insignificant, or fragmented."
    diagnostics={"requested_colors":target,"colors_used":len(used_codes),"selected_codes":used_codes,"utilization_reason":reason,
                 "candidate_count":len(candidates),"candidates":[{"index":c.index,"coverage":c.coverage,"components":c.components,"single_cells":c.single_cells,"tiny_cells":c.tiny_cells,"confetti_ratio":c.confetti_ratio,"contrast":c.contrast,"utility":c.base_utility} for c in candidates]}
    return ids,diagnostics

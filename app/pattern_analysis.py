"""Logical-pattern connected regions and non-destructive confetti scoring."""
from collections import Counter,deque
from dataclasses import dataclass,field
import logging
from math import sqrt
from time import perf_counter

LOG=logging.getLogger(__name__)

@dataclass(frozen=True)
class ConfettiTuning:
    maximum_suspect_size:int=10;similarity_delta_e:float=25.0;strong_edge_delta_e:float=25.0
    size_weight:float=.28;dominance_weight:float=.20;similarity_weight:float=.30;isolation_weight:float=.10;fragmentation_weight:float=.12
    edge_protection_weight:float=.22;transparency_protection_weight:float=.30;line_protection_weight:float=.18
    high_threshold:float=70.0;medium_threshold:float=45.0

DEFAULT_CONFETTI_TUNING=ConfettiTuning()
SIZE_CATEGORIES=((1,"1 cell"),(2,"2 cells"),(3,"3 cells"),(5,"4-5 cells"),(10,"6-10 cells"),(10**18,"11+ cells"))

@dataclass
class PatternRegion:
    region_id:int;code:str;cells:tuple[int,...];size:int;bbox:tuple[int,int,int,int];centroid:tuple[float,float]
    neighbor_counts:dict[str,int]=field(default_factory=dict);transparent_boundary:int=0;outside_boundary:int=0
    dominant_neighbor:str|None=None;dominant_share:float=0.0;dominant_delta_e:float|None=None;edge_protection:float=0.0;line_protection:float=0.0
    score:float=0.0;confidence:str="Low";suggested_replacement:str|None=None
    @property
    def category(self):return size_category(self.size)

@dataclass
class ConfettiAnalysis:
    width:int;height:int;total_drills:int;regions:list[PatternRegion];elapsed_seconds:float;maximum_suspect_size:int=10;stale:bool=False
    @property
    def suspects(self):return [region for region in self.regions if region.size<=self.maximum_suspect_size]
    def confidence_regions(self,confidence):return [region for region in self.suspects if region.confidence==confidence]
    @property
    def metrics(self):
        high=self.confidence_regions("High");tiny=[region for region in self.regions if region.size<=3]
        high_cells=sum(region.size for region in high)
        return {"regions":len(self.regions),"single_cell_regions":sum(region.size==1 for region in self.regions),"regions_2_to_3":sum(2<=region.size<=3 for region in self.regions),
                "tiny_region_cells":sum(region.size for region in tiny),"high_regions":len(high),"high_cells":high_cells,
                "high_percentage":high_cells/self.total_drills*100 if self.total_drills else 0.0,"medium_regions":len(self.confidence_regions("Medium")),
                "low_regions":len(self.confidence_regions("Low")),"affected_cells":sum(region.size for region in self.suspects)}
    @property
    def per_color(self):
        result={}
        for region in self.regions:
            item=result.setdefault(region.code,{"drills":0,"regions":0,"single_regions":0,"tiny_cells":0,"high_cells":0,"suspect_regions":0})
            item["drills"]+=region.size;item["regions"]+=1;item["single_regions"]+=region.size==1;item["tiny_cells"]+=region.size if region.size<=3 else 0
            item["high_cells"]+=region.size if region.confidence=="High" and region.size<=self.maximum_suspect_size else 0;item["suspect_regions"]+=region.size<=self.maximum_suspect_size
        for item in result.values():item["high_percentage"]=item["high_cells"]/item["drills"]*100 if item["drills"] else 0.0
        return result

def size_category(size):
    for maximum,label in SIZE_CATEGORIES:
        if size<=maximum:return label

def _delta_e(first,second):return sqrt(sum((a-b)**2 for a,b in zip(first,second)))

def connected_components(pattern,code=None):
    """Return deterministic 4-connected ``(DMC code, cell indices)`` components."""
    width,height=pattern.width,pattern.height;values=pattern.cell_ids;seen=bytearray(len(values));result=[]
    for start,value in enumerate(values):
        if seen[start] or value is None or (code is not None and value!=code):continue
        queue=deque([start]);seen[start]=1;component=[]
        while queue:
            current=queue.popleft();component.append(current);x=current%width;y=current//width
            for other in (current-1 if x else -1,current+1 if x+1<width else -1,current-width if y else -1,current+width if y+1<height else -1):
                if other>=0 and not seen[other] and values[other]==value:seen[other]=1;queue.append(other)
        result.append((value,component))
    return result

def _region_geometry(region_id,code,cells,width):
    xs=[index%width for index in cells];ys=[index//width for index in cells]
    return PatternRegion(region_id,code,tuple(cells),len(cells),(min(xs),min(ys),max(xs),max(ys)),(sum(xs)/len(xs),sum(ys)/len(ys)))

def _context(region,pattern):
    width,height=pattern.width,pattern.height;values=pattern.cell_ids;neighbors=Counter();transparent=outside=0;own=set(region.cells)
    for current in region.cells:
        x=current%width;y=current//width
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if not (0<=nx<width and 0<=ny<height):outside+=1;continue
            other=ny*width+nx
            if other in own:continue
            value=values[other]
            if value is None:transparent+=1
            elif value!=region.code:neighbors[value]+=1
    region.neighbor_counts=dict(neighbors);region.transparent_boundary=transparent;region.outside_boundary=outside

def _score_region(region,pattern,tiny_count,tuning):
    colored=sum(region.neighbor_counts.values());total_boundary=colored+region.transparent_boundary+region.outside_boundary
    if colored:
        ordered=sorted(region.neighbor_counts.items(),key=lambda item:(-item[1],item[0]));region.dominant_neighbor=ordered[0][0];region.dominant_share=ordered[0][1]/colored
        component_lab=pattern.palette._labs[region.code];region.dominant_delta_e=_delta_e(component_lab,pattern.palette._labs[region.dominant_neighbor])
        region.suggested_replacement=min(ordered,key=lambda item:_delta_e(component_lab,pattern.palette._labs[item[0]])/(item[1]/colored+.15))[0]
        if len(ordered)>=2:
            first_share=ordered[0][1]/colored;second_share=ordered[1][1]/colored;between=_delta_e(pattern.palette._labs[ordered[0][0]],pattern.palette._labs[ordered[1][0]])
            if first_share>=.25 and second_share>=.25:region.edge_protection=min(1.0,between/tuning.strong_edge_delta_e)*(1-abs(first_share-second_share))
    min_x,min_y,max_x,max_y=region.bbox
    if region.size>=3 and (min_x==max_x or min_y==max_y):region.line_protection=.7
    size_scores={1:1.0,2:.85,3:.70,4:.55,5:.55,6:.35,7:.35,8:.35,9:.35,10:.35};size_score=size_scores.get(region.size,0.0)
    similarity=max(0.0,1-(region.dominant_delta_e or tuning.similarity_delta_e)/tuning.similarity_delta_e) if colored else 0.0
    isolation=min(1.0,colored/max(1,total_boundary));fragmentation=min(1.0,max(0,tiny_count-1)/8);transparency_protection=(region.transparent_boundary+region.outside_boundary)/max(1,total_boundary)
    raw=(tuning.size_weight*size_score+tuning.dominance_weight*region.dominant_share+tuning.similarity_weight*similarity+tuning.isolation_weight*isolation+
         tuning.fragmentation_weight*fragmentation-tuning.edge_protection_weight*region.edge_protection-tuning.transparency_protection_weight*transparency_protection-
         tuning.line_protection_weight*region.line_protection)
    region.score=round(max(0.0,min(100.0,raw*100)),2);region.confidence="High" if region.score>=tuning.high_threshold else "Medium" if region.score>=tuning.medium_threshold else "Low"
    if region.confidence=="Low":region.suggested_replacement=None

def analyze_confetti(pattern,tuning=DEFAULT_CONFETTI_TUNING):
    started=perf_counter();LOG.info("Confetti analysis started pattern=%sx%s drills=%s colors=%s",pattern.width,pattern.height,pattern.total_drills,len(pattern.usage))
    raw=connected_components(pattern);regions=[_region_geometry(index,code,cells,pattern.width) for index,(code,cells) in enumerate(raw)];tiny_by_code=Counter(region.code for region in regions if region.size<=tuning.maximum_suspect_size)
    for region in regions:
        if region.size<=tuning.maximum_suspect_size:_context(region,pattern);_score_region(region,pattern,tiny_by_code[region.code],tuning)
    elapsed=perf_counter()-started;analysis=ConfettiAnalysis(pattern.width,pattern.height,pattern.total_drills,regions,elapsed,tuning.maximum_suspect_size);metrics=analysis.metrics
    LOG.info("Confetti analysis completed in %.3f s components=%s High=%s regions/%s cells Medium=%s Low=%s",elapsed,len(regions),metrics["high_regions"],metrics["high_cells"],metrics["medium_regions"],metrics["low_regions"]);return analysis

def region_summary(pattern):
    sizes=[len(cells) for _code,cells in connected_components(pattern)]
    return {"regions":len(sizes),"single_cell_regions":sum(size==1 for size in sizes),"regions_le_3":sum(size<=3 for size in sizes)}

from collections import deque

def connected_components(pattern,code=None):
    seen=set(); result=[]
    for index,value in enumerate(pattern.cell_ids):
        if index in seen or value is None or (code is not None and value!=code):continue
        queue=deque([index]);seen.add(index);component=[]
        while queue:
            current=queue.popleft();component.append(current);x=current%pattern.width;y=current//pattern.width
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                other=ny*pattern.width+nx if 0<=nx<pattern.width and 0<=ny<pattern.height else -1
                if other>=0 and other not in seen and pattern.cell_ids[other]==value:
                    seen.add(other);queue.append(other)
        result.append((value,component))
    return result

def region_summary(pattern):
    sizes=[len(cells) for _code,cells in connected_components(pattern)]
    return {"regions":len(sizes),"single_cell_regions":sum(size==1 for size in sizes),"regions_le_3":sum(size<=3 for size in sizes)}

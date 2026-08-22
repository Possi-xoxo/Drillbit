from collections import Counter, deque
from dataclasses import dataclass
from PIL import Image
from .symbols import ensure_pattern_symbols

@dataclass(frozen=True)
class CellChange:
    index: int
    before: str | None
    after: str | None

@dataclass(frozen=True)
class PatternClipboard:
    width: int
    height: int
    cells: tuple[str | None,...]
    def __post_init__(self):
        if self.width<1 or self.height<1 or len(self.cells)!=self.width*self.height:raise ValueError("Clipboard dimensions do not match its logical cells.")

class PatternModel:
    def __init__(self,width,height,cell_ids,palette,metadata=None,initial_ids=None):
        if len(cell_ids)!=width*height: raise ValueError("Cell grid does not match pattern dimensions.")
        invalid={code for code in cell_ids if code is not None}-set(palette.by_code)
        if invalid: raise ValueError(f"Unknown palette IDs: {sorted(invalid)[:5]}")
        self.width=width; self.height=height; self.cell_ids=list(cell_ids); self.palette=palette; self.metadata=metadata or {}
        self.initial_ids=list(initial_ids if initial_ids is not None else cell_ids); self.usage=Counter(code for code in self.cell_ids if code is not None);ensure_pattern_symbols(self)

    def index(self,x,y):
        if not (0<=x<self.width and 0<=y<self.height): raise IndexError((x,y))
        return y*self.width+x

    def get(self,x,y): return self.cell_ids[self.index(x,y)]

    def _set_index(self,index,code):
        if code is not None and code not in self.palette.by_code: raise ValueError(f"Unknown palette code {code}")
        old=self.cell_ids[index]
        if old==code:return None
        self.cell_ids[index]=code
        if old is not None:
            self.usage[old]-=1
            if self.usage[old]<=0: del self.usage[old]
        if code is not None:self.usage[code]+=1
        return CellChange(index,old,code)

    def set_cell(self,x,y,code):
        change=self._set_index(self.index(x,y),code); return [] if change is None else [change]

    def paint(self,cells,code):
        changes=[]
        for x,y in cells:
            if 0<=x<self.width and 0<=y<self.height:
                change=self._set_index(self.index(x,y),code)
                if change:changes.append(change)
        return changes

    def flood_fill(self,x,y,code):
        target=self.get(x,y)
        if target==code:return []
        queue=deque([(x,y)]); seen={(x,y)}; cells=[]
        while queue:
            cx,cy=queue.popleft(); cells.append((cx,cy))
            for nx,ny in ((cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)):
                if 0<=nx<self.width and 0<=ny<self.height and (nx,ny) not in seen and self.get(nx,ny)==target:
                    seen.add((nx,ny));queue.append((nx,ny))
        return self.paint(cells,code)

    def replace_color(self,old,new):
        return self.paint(((i%self.width,i//self.width) for i,value in enumerate(self.cell_ids) if value==old),new)

    def normalize_rect(self,left,top,right,bottom):
        left,right=sorted((max(0,min(self.width,left)),max(0,min(self.width,right))))
        top,bottom=sorted((max(0,min(self.height,top)),max(0,min(self.height,bottom))))
        return left,top,right,bottom

    def region_cells(self,bounds):
        left,top,right,bottom=self.normalize_rect(*bounds)
        return tuple(self.cell_ids[y*self.width+left:y*self.width+right] for y in range(top,bottom))

    def copy_region(self,bounds):
        left,top,right,bottom=self.normalize_rect(*bounds);rows=self.region_cells((left,top,right,bottom))
        return PatternClipboard(right-left,bottom-top,tuple(value for row in rows for value in row))

    def fill_region(self,bounds,code):
        left,top,right,bottom=self.normalize_rect(*bounds)
        return self.paint(((x,y) for y in range(top,bottom) for x in range(left,right)),code)

    def replace_color_in_region(self,bounds,old,new):
        left,top,right,bottom=self.normalize_rect(*bounds)
        return self.paint(((x,y) for y in range(top,bottom) for x in range(left,right) if self.get(x,y)==old),new)

    def paste_region(self,clipboard,left,top):
        if left<0 or top<0 or left+clipboard.width>self.width or top+clipboard.height>self.height:raise ValueError("Pasted region must fit entirely inside the pattern.")
        return self._paste_cells(clipboard,left,top)

    def _paste_cells(self,clipboard,left,top):
        changes=[]
        for y in range(clipboard.height):
            for x in range(clipboard.width):
                change=self._set_index((top+y)*self.width+left+x,clipboard.cells[y*clipboard.width+x])
                if change:changes.append(change)
        return changes

    def move_region(self,bounds,destination_left,destination_top):
        if not self.supports_transparency:raise ValueError("Moving selections requires a transparency-enabled pattern.")
        left,top,right,bottom=self.normalize_rect(*bounds);clipboard=self.copy_region((left,top,right,bottom))
        if destination_left<0 or destination_top<0 or destination_left+clipboard.width>self.width or destination_top+clipboard.height>self.height:raise ValueError("Moved region must fit entirely inside the pattern.")
        desired={y*self.width+x:None for y in range(top,bottom) for x in range(left,right)}
        for y in range(clipboard.height):
            for x in range(clipboard.width):desired[(destination_top+y)*self.width+destination_left+x]=clipboard.cells[y*clipboard.width+x]
        changes=[]
        for index,value in sorted(desired.items()):
            change=self._set_index(index,value)
            if change:changes.append(change)
        return changes

    def apply_changes(self,changes,forward=True):
        for change in changes: self._set_index(change.index,change.after if forward else change.before)

    def to_image(self,initial=False):
        ids=self.initial_ids if initial else self.cell_ids
        transparent=any(code is None for code in ids);image=Image.new("RGBA" if transparent else "RGB",(self.width,self.height))
        image.putdata([(0,0,0,0) if code is None else (*self.palette.by_code[code].rgb,255) if transparent else self.palette.by_code[code].rgb for code in ids]);return image

    @property
    def total_drills(self):return sum(self.usage.values())

    @property
    def empty_cells(self):return self.width*self.height-self.total_drills

    @property
    def supports_transparency(self):return bool(self.metadata.get("preserve_transparency")) or any(code is None for code in self.cell_ids)

    def used_colors(self): return sorted(((self.palette.by_code[code],count) for code,count in self.usage.items()),key=lambda item:item[1],reverse=True)

class EditCommand:
    def __init__(self,label,changes): self.label=label; self.changes=list(changes)

class UndoStack:
    """Delta-command history for edits already applied interactively.

    ``push`` records completed deltas but deliberately does not reapply them.
    Listeners are notified synchronously after every real history transition.
    """
    def __init__(self): self.commands=[]; self.position=0; self._listeners=[]
    @property
    def can_undo(self): return self.position>0
    @property
    def can_redo(self): return self.position<len(self.commands)
    @property
    def count(self): return len(self.commands)
    @property
    def undo_text(self): return self.commands[self.position-1].label if self.can_undo else ""
    @property
    def redo_text(self): return self.commands[self.position].label if self.can_redo else ""
    def add_listener(self,listener):
        if listener not in self._listeners:self._listeners.append(listener)
        listener(self)
    def _notify(self):
        for listener in tuple(self._listeners):listener(self)
    def push(self,label,changes):
        changes=list(changes)
        if not changes:return False
        self.commands=self.commands[:self.position];self.commands.append(EditCommand(label,changes));self.position+=1;self._notify();return True
    def undo(self,pattern):
        if not self.can_undo:return False
        self.position-=1;pattern.apply_changes(reversed(self.commands[self.position].changes),False);self._notify();return True
    def redo(self,pattern):
        if not self.can_redo:return False
        pattern.apply_changes(self.commands[self.position].changes,True);self.position+=1;self._notify();return True

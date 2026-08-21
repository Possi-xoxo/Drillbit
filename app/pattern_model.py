from collections import Counter, deque
from dataclasses import dataclass
from PIL import Image

@dataclass(frozen=True)
class CellChange:
    index: int
    before: str | None
    after: str | None

class PatternModel:
    def __init__(self,width,height,cell_ids,palette,metadata=None,initial_ids=None):
        if len(cell_ids)!=width*height: raise ValueError("Cell grid does not match pattern dimensions.")
        invalid={code for code in cell_ids if code is not None}-set(palette.by_code)
        if invalid: raise ValueError(f"Unknown palette IDs: {sorted(invalid)[:5]}")
        self.width=width; self.height=height; self.cell_ids=list(cell_ids); self.palette=palette; self.metadata=metadata or {}
        self.initial_ids=list(initial_ids if initial_ids is not None else cell_ids); self.usage=Counter(code for code in self.cell_ids if code is not None)

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

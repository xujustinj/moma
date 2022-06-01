import glob
import os
import os.path as osp
import pickle


class Bidict(dict):
  """
  A many-to-one bidirectional dictionary
  Reference: https://stackoverflow.com/questions/3318625/how-to-implement-an-efficient-bidirectional-hash-table
  """
  def __init__(self, *args, **kwargs):
    super(Bidict, self).__init__(*args, **kwargs)
    self.inverse = {}
    for key, value in self.items():
      self.inverse.setdefault(value, set()).add(key)

  def __setitem__(self, key, value):
    if key in self:
      self.inverse[self[key]].remove(key)
    super(Bidict, self).__setitem__(key, value)
    self.inverse.setdefault(value, set()).add(key)

  def __delitem__(self, key):
    self.inverse[self[key]].remove(key)
    if len(self.inverse[self[key]]) == 0:
      del self.inverse[self[key]]
    super(Bidict, self).__delitem__(key)


class OrderedBidict(dict):
  """
  A one-to-many bidirectional dictionary whose value is a list instead of a set
  """
  def __init__(self, *args, **kwargs):
    super(OrderedBidict, self).__init__(*args, **kwargs)
    self.inverse = {}
    for key, values in self.items():
      for value in values:
        assert value not in self.inverse  # no duplicates
        self.inverse[value] = key

  def __setitem__(self, key, value):
    raise NotImplementedError

  def __delitem__(self, key):
    raise NotImplementedError


class LazyDict(dict):
  def __init__(self, dir_cache, prefix):
    super().__init__()
    self.buffer = {}
    self.dir_cache = dir_cache
    self.path_prefix = osp.join(dir_cache, f'{prefix}_')
    self._keys = [self.removeprefix(x, self.path_prefix) for x in glob.glob(self.path_prefix+'*')]

  def keys(self):
    return self._keys

  def values(self):
    return [self.__getitem__(key) for key in self._keys]

  def items(self):
    raise NotImplementedError

  def __getitem__(self, key):
    if key in self.buffer:
      return self.buffer[key]
    else:
      with open(self.path_prefix+key, 'rb') as f:
        value = pickle.load(f)
        self.buffer[key] = value
        return value

  def __len__(self):
    return len(self._keys)

  def __repr__(self):
    return 'LazyDict()'
  
  # Added for python backwards compatibility
  def removeprefix(self, text, prefix):
      if text.startswith(prefix):
          return text[len(prefix):]
      return text

class Metadatum:
  def __init__(self, ann):
    self.id = ann['activity']['id']
    self.fname = ann['file_name']
    self.num_frames = ann['num_frames']
    self.width = ann['width']
    self.height = ann['height']
    self.duration = ann['duration']

  def get_fid(self, time):
    """ Get the frame ID given a timestamp in seconds
    """
    fps = (self.num_frames-1)/self.duration
    fid = time*fps
    return fid

  def get_time(self, fid):
    raise NotImplementedError

  def __repr__(self):
    return f'Metadatum(id={self.id}, fname={self.fname}, size=({self.num_frames}, {self.height}, {self.width}, 3), ' \
           f'duration={self.duration}'


class Act:
  def __init__(self, ann, taxonomy):
    self.id = ann['id']
    self.cname = ann['class_name']
    self.cid = taxonomy.index(ann['class_name'])
    self.start = ann['start_time']
    self.end = ann['end_time']
    self.ids_sact = [x['id'] for x in ann['sub_activities']]

  def __repr__(self):
    return f'Act(id={self.id}, cname={self.cname}, time=[{self.start}, end={self.end}), num_sacts={len(self.ids_sact)}'


class SAct:
  def __init__(self, ann, taxonomy_sact, taxonomy_actor, taxonomy_object):
    self.id = ann['id']
    self.cname = ann['class_name']
    self.cid = taxonomy_sact.index(ann['class_name'])
    self.start = ann['start_time']
    self.end = ann['end_time']
    self.ids_hoi = [x['id'] for x in ann['higher_order_interactions']]

    # unique entity instances in this sub-activity
    self.__id_actor_to_cid_actor = dict(set([
      (y['id'], taxonomy_actor.index(y['class_name'])) for x in ann['higher_order_interactions'] for y in x['actors']
    ]))
    self.__id_object_to_cid_object = dict(set([
      (y['id'], taxonomy_object.index(y['class_name'])) for x in ann['higher_order_interactions'] for y in x['objects']
    ]))

  @property
  def ids_actor(self):
    return sorted(self.__id_actor_to_cid_actor.keys())

  @property
  def ids_object(self):
    return sorted(self.__id_object_to_cid_object.keys(), key=int)

  @property
  def cids_actor(self):
    return sorted(self.__id_actor_to_cid_actor.values())

  @property
  def cids_object(self):
    return sorted(self.__id_object_to_cid_object.values())

  def get_cid_actor(self, id_actor):
    return self.__id_actor_to_cid_actor[id_actor]

  def get_cid_object(self, id_object):
    return self.__id_object_to_cid_object[id_object]

  def __repr__(self):
    return f'SAct(id={self.id}, cname={self.cname}, time=[{self.start}, end={self.end}), num_hois={len(self.ids_hoi)})'


class HOI:
  def __init__(self, ann, taxonomy_actor, taxonomy_object, taxonomy_ia, taxonomy_ta, taxonomy_att, taxonomy_rel):
    self.id = ann['id']
    self.time = ann['time']
    self.actors = [Entity(x, 'actor', taxonomy_actor) for x in ann['actors']]
    self.objects = [Entity(x, 'object', taxonomy_object) for x in ann['objects']]
    self.ias = [Predicate(x, 'ia', taxonomy_ia) for x in ann['intransitive_actions']]
    self.tas = [Predicate(x, 'ta', taxonomy_ta) for x in ann['transitive_actions']]
    self.atts = [Predicate(x, 'att', taxonomy_att) for x in ann['attributes']]
    self.rels = [Predicate(x, 'rel', taxonomy_rel) for x in ann['relationships']]

  @property
  def ids_actor(self):
    return sorted([actor.id for actor in self.actors])

  @property
  def ids_object(self):
    return sorted([object.id for object in self.objects], key=int)

  def __repr__(self):
    return f'HOI(id={self.id}, time={self.time}, ' \
           f'num_actors={len(self.actors)}, num_objects={len(self.objects)}, ' \
           f'num_ias={len(self.ias)}, num_tas={len(self.tas)}, ' \
           f'num_atts={len(self.atts)}, num_rels={len(self.rels)}, ' \
           f'ids_actor={self.ids_actor}, ids_object={self.ids_object})'


class Clip:
  """ A clip corresponds to a 1 second/5 frames video clip centered at the higher-order interaction
   - <1 second/5 frames if exceeds the raw video boundary
   - Currently, only clips from the test set have been generated
  """
  def __init__(self, ann, neighbors):
    self.id = ann['id']
    self.time = ann['time']
    self.neighbors = neighbors


class BBox:
  def __init__(self, ann):
    self.x, self.y, self.width, self.height = ann

  @property
  def x1(self):
      return self.x

  @property
  def y1(self):
      return self.y

  @property
  def x2(self):
      return self.x+self.width

  @property
  def y2(self):
      return self.y+self.height

  def __repr__(self):
    return f'BBox(x={self.x}, y={self.y}, w={self.width}, h={self.height})'


class Entity:
  def __init__(self, ann, kind, taxonomy):
    self.id = ann['id']  # local instance ID
    self.kind = kind
    self.cname = ann['class_name']
    self.cid = taxonomy.index(self.cname)
    self.bbox = BBox(ann['bbox'])

  def __repr__(self):
    name = ''.join(x.capitalize() for x in self.kind.split('_'))
    return f'{name}(id={self.id}, cname={self.cname})'


class Predicate:
  def __init__(self, ann, kind, taxonomy):
    is_binary = 'target_id' in ann
    self.kind = kind
    self.signature = {x[0]:(x[1:] if is_binary else x[1]) for x in taxonomy}[ann['class_name']]
    self.cname = ann['class_name']
    self.cid = [x[0] for x in taxonomy].index(self.cname)
    self.id_src = ann['source_id']
    self.id_trg = ann['target_id'] if is_binary else None

  def __repr__(self):
    name = ''.join(x.capitalize() for x in self.kind.split('_'))
    id = f'{self.id_src}' if self.id_trg is None else f'{self.id_src} -> {self.id_trg}'
    return f'{name}(id={id}, cname={self.cname})'

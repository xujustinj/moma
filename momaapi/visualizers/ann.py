from collections import defaultdict
import glob
import math
import os
import os.path as osp
import shutil
import tempfile
from typing import Optional

from distinctipy import distinctipy
from matplotlib import font_manager
import PIL.Image as Image
import PIL.ImageDraw as ImageDraw
import PIL.ImageFont as ImageFont
import pygraphviz as pgv
from torchvision import io

from ..moma import MOMA
from ..data import BBox, HOI
from ..utils import assert_type, only, supress_stdout
from .timeline import TimelineVisualizer


class AnnVisualizer:
    def __init__(self, moma: MOMA, vis_dir: Optional[str] = None):
        if vis_dir is None:
            vis_dir = tempfile.mkdtemp()
        else:
            os.makedirs(vis_dir, exist_ok=True)

        self.moma = moma
        self.timeline_visualizer = TimelineVisualizer(moma, vis_dir)

        # paths
        self.vis_dir = vis_dir

        self.sact_dir = osp.join(self.vis_dir, "sact")
        os.makedirs(self.sact_dir, exist_ok=True)

        self.hoi_dir = osp.join(self.vis_dir, "hoi")
        os.makedirs(self.hoi_dir, exist_ok=True)

    @staticmethod
    def _get_palette(ids, alpha=255):
        # distinctipy's representation
        colors_box = distinctipy.get_colors(len(ids))
        colors_text = [
            distinctipy.get_text_color(color_box) for color_box in colors_box
        ]

        # PIL's representation
        colors_box = [
            tuple([int(x * 255) for x in color_box] + [alpha])
            for color_box in colors_box
        ]
        colors_text = [
            tuple([int(x * 255) for x in color_text] + [alpha])
            for color_text in colors_text
        ]

        palette = {
            id: (color_box, color_text)
            for id, color_box, color_text in zip(ids, colors_box, colors_text)
        }
        return palette

    def _draw_bbox(self, ann_hoi: HOI, palette):
        hoi_id = assert_type(ann_hoi.id, str)
        act_id = only(self.moma.get_ids_act(ids_hoi=[hoi_id]))
        metadata = only(self.moma.get_metadata(ids_act=[act_id]))

        path_image = only(self.moma.get_paths(ids_hoi=[hoi_id]))
        image = io.read_image(path_image).permute(1, 2, 0).numpy()
        image = Image.fromarray(image).convert("RGBA")

        x_scale = metadata.width / image.width
        y_scale = metadata.height / image.height
        assert math.isclose(x_scale, y_scale, rel_tol=1e-2)
        scale = math.sqrt(x_scale * y_scale) # geometric mean

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        width_line = int(max(image.size) * 0.003)

        font_props = font_manager.FontProperties(
            family="sans-serif", stretch="extra-condensed", weight="light"
        )
        path_font = font_manager.findfont(font_props)
        font = ImageFont.truetype(path_font, int(max(image.size) * 0.02))

        for entity in ann_hoi.actors + ann_hoi.objects:
            bbox = BBox.scale(entity.bbox, scale_factor=scale)
            y1 = bbox.y1
            x1 = bbox.x1
            y2 = bbox.y2
            x2 = bbox.x2
            width_text, height_text = font.getsize(entity.cname)
            draw.rectangle(
                ((x1, y1), (x2, y2)), width=width_line, outline=palette[entity.id][0]
            )
            draw.rectangle(
                (
                    (x1, y1),
                    (
                        x1 + width_text + 2 * width_line,
                        y1 + height_text + 2 * width_line,
                    ),
                ),
                fill=palette[entity.id][0],
            )
            draw.text(
                (x1 + width_line, y1 + width_line),
                entity.cname,
                fill=palette[entity.id][1],
                font=font,
            )

        image.paste(Image.alpha_composite(image, overlay))

        return image.convert("RGB")

    @supress_stdout
    def show_hoi(self, id_hoi: str, vstack: bool = True):
        path_hoi = osp.join(self.hoi_dir, f"{id_hoi}.png")

        if osp.isfile(path_hoi):
            return path_hoi

        act_id = only(self.moma.get_ids_act(ids_hoi=[id_hoi]))
        ann_hoi = only(self.moma.get_anns_hoi(ids_hoi=[id_hoi]))
        palette = self._get_palette(ann_hoi.ids_actor + ann_hoi.ids_object, alpha=150)

        """ bbox """
        image = self._draw_bbox(ann_hoi, palette)
        path_bbox = osp.join(self.hoi_dir, f"bbox_{id_hoi}.png")
        image.save(path_bbox)

        """ graph """
        G = pgv.AGraph(directed=True, strict=True)

        for actor in ann_hoi.actors:
            G.add_node(
                actor.id,
                label=actor.id,
                xlabel=actor.cname,
                fontcolor="steelblue",
                color="steelblue",
                shape="circle",
            )
        for object in ann_hoi.objects:
            G.add_node(
                object.id,
                label=object.id,
                xlabel=object.cname,
                fontcolor="salmon3",
                color="salmon3",
                shape="circle",
            )
        for predicate in ann_hoi.rels:
            G.add_edge(
                (predicate.id_src, predicate.id_trg),
                label=predicate.cname,
                color="slategray",
                fontcolor="slategray",
                fontsize="10",
                len=2,
            )
        for predicate in ann_hoi.atts:
            G.add_edge(
                (predicate.id_src, predicate.id_src),
                label=predicate.cname,
                color="slategray",
                fontcolor="slategray",
                fontsize="10",
                len=2,
            )

        G.layout("neato")
        G.node_attr["fontname"] = "Arial"
        G.edge_attr["fontname"] = "Arial"
        path_graph = osp.join(self.hoi_dir, f"graph_{id_hoi}.eps")
        G.draw(path_graph)

        """ save """
        image_bbox = Image.open(path_bbox)
        image_graph = Image.open(path_graph)

        width_bbox, height_bbox = image_bbox.size
        width_graph, height_graph = image_graph.size

        if vstack:
            scale = math.ceil(width_bbox / width_graph)
            image_graph.load(scale=scale)
            image_graph = image_graph.resize(
                (width_bbox, round(width_bbox * height_graph / width_graph))
            )

            image = Image.new(
                "RGB", (image_bbox.width, image_bbox.height + image_graph.height)
            )
            image.paste(image_bbox, (0, 0))
            image.paste(image_graph, (0, image_bbox.height))

        else:  # hstack
            scale = math.ceil(height_bbox / height_graph)
            image_graph.load(scale=scale)
            image_graph = image_graph.resize(
                (round(height_bbox * width_graph / height_graph), height_bbox)
            )

            image = Image.new(
                "RGB", (image_bbox.width + image_graph.width, image_bbox.height)
            )
            image.paste(image_bbox, (0, 0))
            image.paste(image_graph, (image_bbox.width, 0))

        image.save(path_hoi)

        # cleanup
        os.remove(path_bbox)
        os.remove(path_graph)
        image_bbox.close()
        image_graph.close()

        return path_hoi

    @supress_stdout
    def show_sact(self, id_sact: str, vstack: bool = True):
        path_sact = osp.join(self.sact_dir, f"{id_sact}.gif")
        if osp.isfile(path_sact):
            return path_sact

        cache_dir = osp.join(self.sact_dir, id_sact)
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
        os.makedirs(cache_dir, exist_ok=False)

        ann_sact = only(self.moma.get_anns_sact(ids_sact=[id_sact]))
        ids_hoi = self.moma.get_ids_hoi(ids_sact=[id_sact])
        anns_hoi = self.moma.get_anns_hoi(ids_hoi=ids_hoi)
        palette = self._get_palette(ann_sact.ids_actor + ann_sact.ids_object, alpha=200)

        """ bbox """
        for i, id_hoi in enumerate(ids_hoi):
            ann_hoi = only(self.moma.get_anns_hoi(ids_hoi=[id_hoi]))
            image = self._draw_bbox(ann_hoi, palette)
            image.save(osp.join(cache_dir, f"bbox_{str(i).zfill(2)}.png"))

        """ graph """
        # get node & edge positions
        info_nodes = []
        for aact_actor in ann_sact.aacts_actor:
            id_actor = aact_actor.id_entity
            cname_actor = aact_actor.cname_entity
            info_nodes.append((id_actor, cname_actor))
        for aact_object in ann_sact.aacts_object:
            id_object = aact_object.id_entity
            cname_object = aact_object.cname_entity
            info_nodes.append((id_object, cname_object))

        info_edges = []
        for ann_hoi in anns_hoi:
            edge_to_labels = defaultdict(list)
            for predicate in ann_hoi.rels:
                edge_to_labels[(predicate.id_src, predicate.id_trg)].append(
                    predicate.cname
                )
            for predicate in ann_hoi.atts:
                edge_to_labels[(predicate.id_src, predicate.id_src)].append(
                    predicate.cname
                )
            for edge, labels in edge_to_labels.items():
                info_edges.append((*edge, "\n".join(labels)))
        info_edges = list(set(info_edges))

        G = pgv.AGraph(directed=True, strict=False)
        for node, label in info_nodes:
            G.add_node(
                node,
                label=node,
                xlabel=label,
                fontcolor="slategray",
                color="slategray",
                shape="circle",
            )
        for node_src, node_trg, label in info_edges:
            G.add_edge(
                (node_src, node_trg),
                label=label,
                color="slategray",
                fontcolor="slategray",
                fontsize="10",
                len=2,
            )
        G.layout("neato")
        G.node_attr["fontname"] = "Arial"
        G.edge_attr["fontname"] = "Arial"

        pos_node = {node: node.attr["pos"] for node in G.nodes()}
        pos_edge = {(*edge, edge.attr["label"]): edge.attr["pos"] for edge in G.edges()}

        G.remove_nodes_from([info_node[0] for info_node in info_nodes])

        # draw graphs
        for i, ann_hoi in enumerate(anns_hoi):
            # draw nodes
            data_node = []
            for info_node in info_nodes:
                if info_node in [(actor.id, actor.cname) for actor in ann_hoi.actors]:
                    color = "steelblue"
                elif info_node in [
                    (object.id, object.cname) for object in ann_hoi.objects
                ]:
                    color = "salmon3"
                else:
                    color = "grey"
                data_node.append((*info_node, color))

            for node, label, color in data_node:
                pos = pos_node[node]
                G.add_node(
                    node,
                    label=node,
                    xlabel=label,
                    pos=pos,
                    fontcolor=color,
                    color=color,
                    shape="circle",
                )

            # draw edges
            edge_to_labels = defaultdict(list)
            for predicate in ann_hoi.rels:
                edge_to_labels[(predicate.id_src, predicate.id_trg)].append(
                    predicate.cname
                )
            for predicate in ann_hoi.atts:
                edge_to_labels[(predicate.id_src, predicate.id_src)].append(
                    predicate.cname
                )
            edge_to_label = {
                edge: "\n".join(labels) for edge, labels in edge_to_labels.items()
            }

            data_edge = []
            for info_edge in info_edges:
                if info_edge in [
                    (*edge, label) for edge, label in edge_to_label.items()
                ]:
                    data_edge.append((*info_edge, "slategray"))
                else:
                    data_edge.append((*info_edge, "#00000000"))

            for node_src, node_trg, label, color in data_edge:
                pos = pos_edge[(node_src, node_trg, label)]
                G.add_edge(
                    (node_src, node_trg),
                    label=label,
                    pos=pos,
                    color=color,
                    fontcolor=color,
                    fontsize="10",
                    len=2,
                )

            G.draw(osp.join(cache_dir, f"graph_{str(i).zfill(2)}.eps"))
            G.remove_nodes_from([info_node[0] for info_node in info_nodes])

            id_act = only(self.moma.get_ids_act(ids_sact=[id_sact]))
            id_hoi = ann_hoi.id
            path_timeline = osp.join(cache_dir, f"timeline_{str(i).zfill(2)}.png")
            self.timeline_visualizer.show(
                id_act=id_act, id_sact=id_sact, id_hoi=id_hoi, path=path_timeline
            )

        """ save """
        paths_bbox = sorted(glob.glob(osp.join(cache_dir, "bbox_*.png")))
        paths_graph = sorted(glob.glob(osp.join(cache_dir, "graph_*.eps")))
        paths_timeline = sorted(glob.glob(osp.join(cache_dir, f"timeline_*.png")))

        images_bbox = [Image.open(path_bbox) for path_bbox in paths_bbox]
        images_graph = [Image.open(path_graph) for path_graph in paths_graph]
        images_timeline = [
            Image.open(path_timeline) for path_timeline in paths_timeline
        ]

        assert all(image_bbox.size == images_bbox[0].size for image_bbox in images_bbox)
        assert all(
            image_graph.size == images_graph[0].size for image_graph in images_graph
        )
        assert all(
            image_timeline.size == images_timeline[0].size
            for image_timeline in images_timeline
        )

        width_bbox, height_bbox = images_bbox[0].size
        width_graph, height_graph = images_graph[0].size
        width_timeline, height_timeline = images_timeline[0].size

        images = []
        if vstack:
            scale = math.ceil(width_bbox / width_graph)
            for image_bbox, image_graph, image_timeline in zip(
                images_bbox, images_graph, images_timeline
            ):
                image_graph.load(scale=scale)
                image_graph = image_graph.resize(
                    (width_bbox, round(width_bbox * height_graph / width_graph))
                )
                image_timeline = image_timeline.resize(
                    (width_bbox, round(width_bbox * height_timeline / width_timeline))
                )
                image = Image.new(
                    "RGB",
                    (
                        image_bbox.width,
                        image_bbox.height + image_graph.height + image_timeline.height,
                    ),
                )
                image.paste(image_bbox, (0, 0))
                image.paste(image_graph, (0, image_bbox.height))
                image.paste(image_timeline, (0, image_bbox.height + image_graph.height))
                images.append(image)

        else:  # hstack
            scale = math.ceil(height_bbox / height_graph)
            for image_bbox, image_graph, image_timeline in zip(
                images_bbox, images_graph, images_timeline
            ):
                image_graph.load(scale=scale)
                image_graph = image_graph.resize(
                    (round(height_bbox * width_graph / height_graph), height_bbox)
                )
                image_timeline = image_timeline.resize(
                    (
                        image_bbox.width + image_graph.width,
                        round(
                            (image_bbox.width + image_graph.width)
                            * height_timeline
                            / width_timeline
                        ),
                    )
                )
                image = Image.new(
                    "RGB",
                    (
                        image_bbox.width + image_graph.width,
                        image_bbox.height + image_timeline.height,
                    ),
                )
                image.paste(image_bbox, (0, 0))
                image.paste(image_graph, (image_bbox.width, 0))
                image.paste(image_timeline, (0, image_bbox.height))
                images.append(image)

        images[0].save(
            path_sact,
            format="GIF",
            append_images=images[1:],
            save_all=True,
            duration=250,
            loop=0,
        )

        # cleanup
        shutil.rmtree(cache_dir)
        [image_bbox.close() for image_bbox in images_bbox]
        [image_graph.close() for image_graph in images_graph]
        [image_timeline.close() for image_timeline in images_timeline]

        return path_sact

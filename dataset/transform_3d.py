from typing import Any
import numpy as np
from numpy import random
import mmcv
# from mmcv.parallel import DataContainer as DC
# from mmdet3d.datasets.pipelines import DefaultFormatBundle3D

class PadMultiViewImage(object):
    """Pad the multi-view image.
    There are two padding modes: (1) pad to a fixed size and (2) pad to the
    minimum size that is divisible by some number.
    Added keys are "pad_shape", "pad_fixed_size", "pad_size_divisor",
    Args:
        size (tuple, optional): Fixed padding size.
        size_divisor (int, optional): The divisor of padded size.
        pad_val (float, optional): Padding value, 0 by default.
    """

    def __init__(self, size=None, size_divisor=None, pad_val=0):
        self.size = size
        self.size_divisor = size_divisor
        self.pad_val = pad_val
        # only one of size and size_divisor should be valid
        assert size is not None or size_divisor is not None
        if size is not None:
            self.size_divisor = size_divisor = None
        assert size is None or size_divisor is None

    def _pad_img(self, results):
        """Pad images according to ``self.size``."""
        if self.size is not None:
            padded_img = [mmcv.impad(
                img, shape=self.size, pad_val=self.pad_val) for img in results['img']]
            if 'extra_img' in results:
                padded_extra_img = [mmcv.impad(
                    img, shape=self.size, pad_val=self.pad_val) for img in results['extra_img']]
            if 'ori_img' in results:
                padded_ori_img = [mmcv.impad(
                    img, shape=self.size, pad_val=self.pad_val) for img in results['ori_img']]
        elif self.size_divisor is not None:
            padded_img = [mmcv.impad_to_multiple(
                img, self.size_divisor, pad_val=self.pad_val) for img in results['img']]
            if 'extra_img' in results:
                padded_extra_img = [mmcv.impad_to_multiple(
                    img, self.size_divisor, pad_val=self.pad_val) for img in results['extra_img']]
            if 'ori_img' in results:
                padded_ori_img = [mmcv.impad_to_multiple(
                    img, self.size_divisor, pad_val=self.pad_val) for img in results['ori_img']]

        # results['ori_shape'] = [img.shape for img in results['img']]
        results['img'] = padded_img
        # results['img_shape'] = [img.shape for img in padded_img]
        # results['pad_shape'] = [img.shape for img in padded_img]
        results['pad_fixed_size'] = self.size
        results['pad_size_divisor'] = self.size_divisor
        if 'extra_img' in results:
            results['extra_img'] = padded_extra_img
        if 'ori_img' in results:
            results['ori_img'] = padded_ori_img

    def __call__(self, results):
        """Call function to pad images, masks, semantic segmentation maps.
        Args:
            results (dict): Result dict from loading pipeline.
        Returns:
            dict: Updated result dict.
        """
        self._pad_img(results)
        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += f'(size={self.size}, '
        repr_str += f'size_divisor={self.size_divisor}, '
        repr_str += f'pad_val={self.pad_val})'
        return repr_str


class NormalizeMultiviewImage(object):
    """Normalize the image.
    Added key is "img_norm_cfg".
    Args:
        mean (sequence): Mean values of 3 channels.
        std (sequence): Std values of 3 channels.
        to_rgb (bool): Whether to convert the image from BGR to RGB,
            default is true.
    """

    def __init__(self, mean, std, to_rgb=True):
        self.mean = np.array(mean, dtype=np.float32)
        self.std = np.array(std, dtype=np.float32)
        self.to_rgb = to_rgb


    def __call__(self, results):
        """Call function to normalize images.
        Args:
            results (dict): Result dict from loading pipeline.
        Returns:
            dict: Normalized results, 'img_norm_cfg' key is added into
                result dict.
        """

        results['img'] = [mmcv.imnormalize(img, self.mean, self.std, self.to_rgb) for img in results['img']]
        results['img_norm_cfg'] = dict(
            mean=self.mean, std=self.std, to_rgb=self.to_rgb)
        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += f'(mean={self.mean}, std={self.std}, to_rgb={self.to_rgb})'
        return repr_str
    
class RandomFlip(object):

    def __init__(self, prob=0.5) -> None:
        self.prob = prob

    def __call__(self, results):
        flip = random.random() < self.prob
        if flip:
            results['img'] = [mmcv.imflip(img) for img in results['img']]
        results['flip'] = flip
        return results

class PhotoMetricDistortionMultiViewImage:
    """Apply photometric distortion to image sequentially, every transformation
    is applied with a probability of 0.5. The position of random contrast is in
    second or second to last.
    1. random brightness
    2. random contrast (mode 0)
    3. convert color from BGR to HSV
    4. random saturation
    5. random hue
    6. convert color from HSV to BGR
    7. random contrast (mode 1)
    8. randomly swap channels
    Args:
        brightness_delta (int): delta of brightness.
        contrast_range (tuple): range of contrast.
        saturation_range (tuple): range of saturation.
        hue_delta (int): delta of hue.
    
    brightness_delta = 8
    contrast_range = (0.9, 1.1)
    saturation_range = (0.9, 1.1)
    hue_delta = 8
    use_swap_channel = False
    """

    def __init__(self,
                 brightness_delta=32,
                 contrast_range=(0.8, 1.2),
                 saturation_range=(0.8, 1.2),
                 hue_delta=18,
                 use_swap_channel=True):
        self.brightness_delta = brightness_delta
        self.contrast_lower, self.contrast_upper = contrast_range
        self.saturation_lower, self.saturation_upper = saturation_range
        self.hue_delta = hue_delta
        self.use_swap_channel = use_swap_channel

    def __call__(self, results):
        """Call function to perform photometric distortion on images.
        Args:
            results (dict): Result dict from loading pipeline.
        Returns:
            dict: Result dict with images distorted.
        """
        imgs = results['img']
        new_imgs = []
        for img in imgs:
            assert img.dtype == np.float32, \
                'PhotoMetricDistortion needs the input image of dtype np.float32,'\
                ' please set "to_float32=True" in "LoadImageFromFile" pipeline'
            # random brightness
            if random.randint(2):
                delta = random.uniform(-self.brightness_delta,
                                    self.brightness_delta)
                img += delta

            # mode == 0 --> do random contrast first
            # mode == 1 --> do random contrast last
            mode = random.randint(2)
            if mode == 1:
                if random.randint(2):
                    alpha = random.uniform(self.contrast_lower,
                                        self.contrast_upper)
                    img *= alpha

            # convert color from BGR to HSV
            img = mmcv.bgr2hsv(img)

            # random saturation
            if random.randint(2):
                img[..., 1] *= random.uniform(self.saturation_lower,
                                            self.saturation_upper)

            # random hue
            if random.randint(2):
                img[..., 0] += random.uniform(-self.hue_delta, self.hue_delta)
                img[..., 0][img[..., 0] > 360] -= 360
                img[..., 0][img[..., 0] < 0] += 360

            # convert color from HSV to BGR
            img = mmcv.hsv2bgr(img)

            # random contrast
            if mode == 0:
                if random.randint(2):
                    alpha = random.uniform(self.contrast_lower,
                                        self.contrast_upper)
                    img *= alpha

            # randomly swap channels
            if random.randint(2) and self.use_swap_channel:
                img = img[..., random.permutation(3)]
            new_imgs.append(img)
        results['img'] = new_imgs
        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += f'(\nbrightness_delta={self.brightness_delta},\n'
        repr_str += 'contrast_range='
        repr_str += f'{(self.contrast_lower, self.contrast_upper)},\n'
        repr_str += 'saturation_range='
        repr_str += f'{(self.saturation_lower, self.saturation_upper)},\n'
        repr_str += f'hue_delta={self.hue_delta})'
        return repr_str



# @PIPELINES.register_module()
# class CustomCollect3D(object):
#     """Collect data from the loader relevant to the specific task.
#     This is usually the last stage of the data loader pipeline. Typically keys
#     is set to some subset of "img", "proposals", "gt_bboxes",
#     "gt_bboxes_ignore", "gt_labels", and/or "gt_masks".
#     The "img_meta" item is always populated.  The contents of the "img_meta"
#     dictionary depends on "meta_keys". By default this includes:
#         - 'img_shape': shape of the image input to the network as a tuple \
#             (h, w, c).  Note that images may be zero padded on the \
#             bottom/right if the batch tensor is larger than this shape.
#         - 'scale_factor': a float indicating the preprocessing scale
#         - 'flip': a boolean indicating if image flip transform was used
#         - 'filename': path to the image file
#         - 'ori_shape': original shape of the image as a tuple (h, w, c)
#         - 'pad_shape': image shape after padding
#         - 'lidar2img': transform from lidar to image
#         - 'depth2img': transform from depth to image
#         - 'cam2img': transform from camera to image
#         - 'pcd_horizontal_flip': a boolean indicating if point cloud is \
#             flipped horizontally
#         - 'pcd_vertical_flip': a boolean indicating if point cloud is \
#             flipped vertically
#         - 'box_mode_3d': 3D box mode
#         - 'box_type_3d': 3D box type
#         - 'img_norm_cfg': a dict of normalization information:
#             - mean: per channel mean subtraction
#             - std: per channel std divisor
#             - to_rgb: bool indicating if bgr was converted to rgb
#         - 'pcd_trans': point cloud transformations
#         - 'sample_idx': sample index
#         - 'pcd_scale_factor': point cloud scale factor
#         - 'pcd_rotation': rotation applied to point cloud
#         - 'pts_filename': path to point cloud file.
#     Args:
#         keys (Sequence[str]): Keys of results to be collected in ``data``.
#         meta_keys (Sequence[str], optional): Meta keys to be converted to
#             ``mmcv.DataContainer`` and collected in ``data[img_metas]``.
#             Default: ('filename', 'ori_shape', 'img_shape', 'lidar2img',
#             'depth2img', 'cam2img', 'pad_shape', 'scale_factor', 'flip',
#             'pcd_horizontal_flip', 'pcd_vertical_flip', 'box_mode_3d',
#             'box_type_3d', 'img_norm_cfg', 'pcd_trans',
#             'sample_idx', 'pcd_scale_factor', 'pcd_rotation', 'pts_filename')
#     """

#     def __init__(self,
#                  keys,
#                  meta_keys=('filename', 'ori_shape', 'img_shape', 'lidar2img',
#                             'depth2img', 'cam2img', 'pad_shape',
#                             'scale_factor', 'flip', 'pcd_horizontal_flip',
#                             'pcd_vertical_flip', 'box_mode_3d', 'box_type_3d',
#                             'img_norm_cfg', 'pcd_trans', 'sample_idx', 'prev_idx', 'next_idx',
#                             'pcd_scale_factor', 'pcd_rotation', 'pts_filename',
#                             'transformation_3d_flow', 'scene_token',
#                             'can_bus',
#                             )):
#         self.keys = keys
#         self.meta_keys = meta_keys

#     def __call__(self, results):
#         """Call function to collect keys in results. The keys in ``meta_keys``
#         will be converted to :obj:`mmcv.DataContainer`.
#         Args:
#             results (dict): Result dict contains the data to collect.
#         Returns:
#             dict: The result dict contains the following keys
#                 - keys in ``self.keys``
#                 - ``img_metas``
#         """
       
#         data = {}
#         img_metas = {}
      
#         for key in self.meta_keys:
#             if key in results:
#                 img_metas[key] = results[key]

#         data['img_metas'] = DC(img_metas, cpu_only=True)
#         for key in self.keys:
#             data[key] = results[key]
#         return data

#     def __repr__(self):
#         """str: Return a string that describes the module."""
#         return self.__class__.__name__ + \
#             f'(keys={self.keys}, meta_keys={self.meta_keys})'



class RandomScaleImageMultiViewImage(object):
    """Random scale the image
    Args:
        scales
    """

    def __init__(self, scales=[], ref_focal_len=None, random_scale=None, pad_scale_rate=None):
        self.scales = scales
        self.ref_focal_len = ref_focal_len
        if random_scale is not None:
            assert isinstance(random_scale, list) and len(random_scale) == 2 and ref_focal_len is None
            # assert random_scale[1] <= 1.0 # TODO
        if pad_scale_rate is None:
            pad_scale_rate = [scales[0]] * 2
        self.pad_scale_rate = pad_scale_rate
        self.random_scale = random_scale
        assert len(self.scales)==1

    def __call__(self, results):
        """Call function to pad images, masks, semantic segmentation maps.
        Args:
            results (dict): Result dict from loading pipeline.
        Returns:
            dict: Updated result dict.
        """
        # rand_ind = np.random.permutation(range(len(self.scales)))[0]
        if self.ref_focal_len is None:
            if self.random_scale is not None:
                focal_ratios = np.random.rand(len(results['img'])) * (self.random_scale[1] - self.random_scale[0]) + self.random_scale[0]
                rand_scales = [self.scales[0] * focal_ratio for focal_ratio in focal_ratios]
                results['focal_ratios'] = focal_ratios.tolist()
            else:
                rand_scales = self.scales * len(results['img'])
        else:
            focal_lens = results['metas']['intrinsic'][:, 0, 0]
            focal_ratios = [self.ref_focal_len * 1.0 / focal_len for focal_len in focal_lens]
            rand_scales = [self.scales[0] * focal_ratio for focal_ratio in focal_ratios]
            results['focal_ratios'] = focal_ratios
        
        results['focal_ratios_x'] = [scale / self.pad_scale_rate[1] for scale in rand_scales]
        results['focal_ratios_y'] = [scale / self.pad_scale_rate[0] for scale in rand_scales]

        y_size = [int(img.shape[0] * scale) for img, scale in zip(results['img'], rand_scales)]
        x_size = [int(img.shape[1] * scale) for img, scale in zip(results['img'], rand_scales)]
        # scale_factor = np.eye(4)
        # scale_factor[0, 0] *= rand_scale
        # scale_factor[1, 1] *= rand_scale
        results['img'] = [mmcv.imresize(img, (x_size[idx], y_size[idx]), return_scale=False) for idx, img in
                          enumerate(results['img'])]
        # lidar2img = [scale_factor @ l2i for l2i in results['lidar2img']]
        # results['lidar2img'] = lidar2img
        # results['img_shape'] = [img.shape for img in results['img']]
        # results['ori_shape'] = [img.shape for img in results['img']]

        return results


    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += f'(size={self.scales}, '
        return repr_str
    
if __name__ == '__main__':

    from mmcv.image.io import imread
    import mmengine, os

    root = 'data/nuscenes'
    pkl = mmengine.load('data/nuscenes_infos_val_sweeps.pkl')
    infos = pkl['infos']['e7ef871f77f44331aefdebc24ec034b7']

    img_paths = []
    for k, v in infos[0]['data'].items():
        if 'CAM' in k:
            img_paths.append(os.path.join(root, v['filename']))

    def read_surround_imgs(img_paths, crop_size=[768, 1600]):
        imgs = []
        for filename in img_paths:
            imgs.append(
                imread(filename, 'unchanged').astype(np.float32))
        imgs = [img[:crop_size[0], :crop_size[1], :] for img in imgs]
        return imgs

    flip_aug = RandomFlip(1.0)
    imgs = read_surround_imgs(img_paths)
    img_dict = {
        'img': imgs}
    img_dict = flip_aug(img_dict)
    pass
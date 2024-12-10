import os
import numpy as np
import torch
from torchvision.models import resnet50
from generative.metrics import FIDMetric

from stai_utils.evaluations.models.resnet import resnet10
from stai_utils.evaluations.util import create_dataloader_from_dir


def _get_medicalnet_model():
    res10 = resnet10()
    res10.conv_seg = torch.nn.Sequential(
        torch.nn.AdaptiveAvgPool3d(1), torch.nn.Flatten()
    )
    res10 = torch.nn.DataParallel(res10)
    ckpt = torch.load(
        "/hai/scratch/alanqw/models/MedicalNet/MedicalNet_pytorch_files2/pretrain/resnet_10.pth"
    )
    res10.load_state_dict(ckpt["state_dict"], strict=False)
    res10.eval()
    return res10


def _get_imagenet_model():
    res50 = resnet50(weights="ResNet50_Weights.DEFAULT")
    res50.eval()
    return res50


def _extract_medicalnet_features_to_dir(
    loader, dest_dir, feature_extractor, device, skip_existing=False
):
    def __itensity_normalize_one_volume__(volume):
        """
        From MedicalNet repository: https://github.com/Tencent/MedicalNet/blob/master/datasets/brains18.py.
        They do data resizing and z-score normalization before feeding the data to the model.

        normalize the itensity of an nd volume based on the mean and std of nonzeor region
        inputs:
            volume: the input nd volume
        outputs:
            out: the normalized nd volume
        """

        pixels = volume[volume > 0]
        mean = pixels.mean()
        std = pixels.std()
        out = (volume - mean) / std
        out_random = np.random.normal(0, 1, size=volume.shape)
        out[volume == 0] = out_random[volume == 0]
        return out

    for i, data in enumerate(loader):
        save_path = os.path.join(dest_dir, f"feat_{i}.npz")
        if skip_existing and os.path.exists(save_path):
            print(f"Skipping because {save_path} already exists...")
            continue
        image = torch.tensor(data["image"]).float().to(device)
        image = __itensity_normalize_one_volume__(image)
        age = data["age"]
        sex = data["sex"]
        feat = feature_extractor(image)

        np.savez(save_path, feat=feat[0].cpu().detach().numpy(), age=age, sex=sex)


def _extract_imagenet_features_to_dir(
    loader, dest_dir, feature_extractor, device, skip_existing=False
):
    # transforms to convert the input image to the format expected by the model
    def subtract_mean(x: torch.Tensor) -> torch.Tensor:
        """Normalize an input image by subtracting the mean."""
        mean = [0.406, 0.456, 0.485]
        x[:, 0, :, :] -= mean[0]
        x[:, 1, :, :] -= mean[1]
        x[:, 2, :, :] -= mean[2]
        return x

    def _get_imagenet_features(image, model):
        """Get features from the input image."""
        # If input has just 1 channel, repeat channel to have 3 channels
        if image.shape[1]:
            image = image.repeat(1, 3, 1, 1)

        # Change order from 'RGB' to 'BGR'
        image = image[:, [2, 1, 0], ...]

        # Subtract mean used during training
        image = subtract_mean(image)

        # Get model outputs
        with torch.no_grad():
            feature_image = model(image)

        return feature_image

    for i, data in enumerate(loader):
        # Convert to 2d
        image = data["image"]
        image = image[:, :, image.shape[2] // 2]
        save_path = os.path.join(dest_dir, f"feat_{i}.npz")
        if skip_existing and os.path.exists(save_path):
            print(f"Skipping because {save_path} already exists...")
            continue
        image = torch.tensor(image).float().to(device)
        age = data["age"]
        sex = data["sex"]
        feat = _get_imagenet_features(image, feature_extractor)

        np.savez(save_path, feat=feat[0].cpu().detach().numpy(), age=age, sex=sex)


def evaluate_fid_medicalnet3d(
    real_img_loader,
    fake_img_loader,
    real_feat_dir,
    fake_feat_dir,
    device,
    skip_existing,
):
    # Load the medicalnet model
    medicalnet = _get_medicalnet_model().to(device)

    # Extract features from the real and fake samples
    print("Extracting medicalnet features...")
    _extract_medicalnet_features_to_dir(
        real_img_loader, real_feat_dir, medicalnet, device, skip_existing=skip_existing
    )
    _extract_medicalnet_features_to_dir(
        fake_img_loader, fake_feat_dir, medicalnet, device, skip_existing=skip_existing
    )

    real_feat_loader = create_dataloader_from_dir(real_feat_dir)
    fake_feat_loader = create_dataloader_from_dir(fake_feat_dir)

    real_feats = []
    fake_feats = []
    for real, fake in zip(real_feat_loader, fake_feat_loader):
        real_feats.append(real["feat"])
        fake_feats.append(fake["feat"])
    return FIDMetric()(torch.vstack(fake_feats), torch.vstack(real_feats)).item()


def evaluate_fid_imagenet2d(
    real_img_loader,
    fake_img_loader,
    real_feat_dir,
    fake_feat_dir,
    device,
    skip_existing,
):
    # Load the imagenet model
    imagenet = _get_imagenet_model().to(device)

    # Extract features from the real and fake samples
    print("Extracting imagenet features...")
    _extract_imagenet_features_to_dir(
        real_img_loader, real_feat_dir, imagenet, device, skip_existing=skip_existing
    )
    _extract_imagenet_features_to_dir(
        fake_img_loader, fake_feat_dir, imagenet, device, skip_existing=skip_existing
    )

    real_feat_loader = create_dataloader_from_dir(real_feat_dir)
    fake_feat_loader = create_dataloader_from_dir(fake_feat_dir)

    real_feats = []
    fake_feats = []
    for real, fake in zip(real_feat_loader, fake_feat_loader):
        real_feats.append(real["feat"])
        fake_feats.append(fake["feat"])
    return FIDMetric()(torch.vstack(fake_feats), torch.vstack(real_feats)).item()

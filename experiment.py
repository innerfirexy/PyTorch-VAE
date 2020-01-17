import math
import torch
from torch import optim
from models import BaseVAE
from models.types_ import *
import pytorch_lightning as pl
from torchvision import transforms
import torchvision.utils as vutils
from torchvision.datasets import CelebA
from torch.utils.data import DataLoader



class VAEXperiment(pl.LightningModule):

    def __init__(self,
                 vae_model: BaseVAE,
                 params: dict) -> None:
        super(VAEXperiment, self).__init__()

        self.model = vae_model
        self.params = params
        self.curr_device = None

    def forward(self, input: Tensor, **kwargs) -> Tensor:
        return self.model(input, **kwargs)

    def training_step(self, batch, batch_idx):
        real_img, labels = batch
        self.curr_device = real_img.device

        results = self.forward(real_img, labels = labels)

        train_loss = self.model.loss_function(*results,
                                              M_N = self.params['batch_size']/ self.num_train_imgs )

        self.logger.experiment.log({key: val.item() for key, val in train_loss.items()})

        return train_loss

    def validation_step(self, batch, batch_idx):
        real_img, labels = batch
        results = self.forward(real_img, labels = labels)
        val_loss = self.model.loss_function(*results,
                                            M_N = self.params['batch_size']/ self.num_train_imgs)

        return val_loss

    def validation_end(self, outputs):
        avg_loss = torch.stack([x['loss'] for x in outputs]).mean()
        tensorboard_logs = {'avg_val_loss': avg_loss}
        self.sample_images()
        return {'val_loss': avg_loss, 'log': tensorboard_logs}

    def sample_images(self):
        z = torch.randn(self.params['batch_size'],
                        self.model.latent_dim)

        if self.on_gpu:
            z = z.cuda(self.curr_device)

        samples = self.model.decode(z).cpu()

        vutils.save_image(samples.data,
                          f"{self.logger.save_dir}/{self.logger.name}/sample_{self.current_epoch}.png",
                          normalize=True,
                          nrow=int(math.sqrt(self.params['batch_size'])))

        # Get sample reconstruction image
        test_input, _ = next(iter(self.sample_dataloader))
        test_input = test_input.cuda(self.curr_device)
        recons = self.model(test_input)

        vutils.save_image(recons[0].data,
                          f"{self.logger.save_dir}/{self.logger.name}/recons_{self.current_epoch}.png",
                          normalize=True,
                          nrow=int(math.sqrt(self.params['batch_size'])))
        del test_input, recons, samples, z



    def configure_optimizers(self):
        optimizer = optim.Adam(self.model.parameters(), lr=self.params['LR'])
        scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma = self.params['scheduler_gamma'])
        return [optimizer] #, [scheduler]

    @pl.data_loader
    def train_dataloader(self):
        transform = self.data_transforms()
        dataset = CelebA(root = self.params['data_path'],
                         split = "train",
                         transform=transform,
                         download=False)
        self.num_train_imgs = len(dataset)
        return DataLoader(dataset,
                          batch_size= self.params['batch_size'],
                          shuffle = True,
                          drop_last=True)

    @pl.data_loader
    def val_dataloader(self):
        transform = self.data_transforms()


        self.sample_dataloader =  DataLoader(CelebA(root = self.params['data_path'],
                                                    split = "test",
                                                    transform=transform,
                                                    download=False),
                                             batch_size= self.params['batch_size'],
                                             shuffle = True,
                                             drop_last=True)
        return self.sample_dataloader

    def data_transforms(self):
        SetRange = transforms.Lambda(lambda X: 2 * X - 1.)
        transform = transforms.Compose([transforms.RandomHorizontalFlip(),
                                        transforms.CenterCrop(148),
                                        transforms.Resize(self.params['img_size']),
                                        transforms.ToTensor(),
                                        SetRange])
        return transform

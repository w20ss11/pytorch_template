import os
import argparse
import numpy as np
from datetime import datetime
import json
import pdb
import albumentations as A
import torch
from torch.utils.data import DataLoader
from torch import nn
import torch.backends.cudnn as cudnn
from torch.optim import lr_scheduler

from model.model import ModelNet
from dataset.CustomDataset import CustomDataset
from utils.log import get_logger
from utils.averageMeter import AverageMeter

############################ PARAMS ################################################################
parser = argparse.ArgumentParser(description='params')
parser.add_argument('--epoch', type=int, default=10, help='Number of epochs to train.')
parser.add_argument('--train_data_path', type=str, default="D:/code/pytorch_template/data/train.txt", help='')
parser.add_argument('--test_data_path',  type=str, default="D:/code/pytorch_template/data/test.txt", help='')
parser.add_argument('--width',  type=int, default="32", help='the width of image')
parser.add_argument('--height', type=int, default="32", help='the height of image')
parser.add_argument('--batch_size', type=int, default="16", help='the batch size of per train data')
parser.add_argument('--init_lr', type=float, default="0.001", help='learning rate')
parser.add_argument('--test_freq', type=int, default=5, help='the frequency to test model')
parser.add_argument('--save_path', type=str, default="./save", help='model save dir')
parser.add_argument('--save_freq', type=int, default="5", help='')
parser.add_argument('--devides', type=int, default="5", help='')
parser.add_argument('--num_workers', type=int, default="0", help='')
parser.add_argument('--num_classes', type=int, default="2", help='')
args = parser.parse_args()

config_path = "./config.json"
fp_json = open(config_path, "r", encoding="utf-8")
json_content = json.load(fp_json)
gpu_ids = json_content['device']
date_str = datetime.now().strftime(r'%m%d_%H%M%S')
log_path = os.path.join(args.save_path, date_str, "log.txt")
logger = get_logger(log_path)

############################ SEED ################################################################
SEED = 123
torch.manual_seed(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
np.random.seed(SEED)

############################ SEED ################################################################
os.environ['CUDA_VISIBLE_DEVICES'] = gpu_ids
use_cuda = 0
if torch.cuda.is_available():
    use_cuda = 1
    cudnn.benchmark = True
kwargs = {'num_workers': args.num_workers, 'pin_memory': True} if use_cuda else {'num_workers': args.num_workers}
device_ids = range(torch.cuda.device_count())

############################ MODEL ################################################################
transforms = A.Compose([ #todo random 
                A.RandomCrop(width=32, height=32),
                A.HorizontalFlip(p=1),
                A.RandomBrightnessContrast(p=1),
            ])
train_dataset = CustomDataset(txt_path=args.train_data_path, width=args.width, height=args.height, transform=transforms)
test_dataset  = CustomDataset(txt_path=args.test_data_path,  width=args.width, height=args.height, transform=transforms)
train_loader = DataLoader(dataset=train_dataset, batch_size=args.batch_size, shuffle=True, **kwargs)
test_loader  = DataLoader(dataset=test_dataset,  batch_size=args.batch_size, shuffle=True, **kwargs)
criterion = nn.CrossEntropyLoss()
model = ModelNet(args.num_classes, criterion)
optimizer = torch.optim.Adam(model.parameters(), lr=args.init_lr)
scheduler = lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.1)

############################ RESUME ###############################################################
start_epoch = 1
save_files = os.listdir(args.save_path)
save_models = {}
max_epoch = -1
for file in save_files:
    if file.endswith(".pth"):
        epoch_num = int(file[file.rfind('_')+1:file.rfind('.')])
        save_models[epoch_num] = os.path.join(args.save_path, file)
        max_epoch = epoch_num if epoch_num > max_epoch else max_epoch
if max_epoch != -1:
    checkpoint = torch.load(save_models[max_epoch])
    model.load_state_dict(checkpoint['model'])
    optimizer.load_state_dict(checkpoint['optimizer'])
    epoch = checkpoint['epoch']
    start_epoch = epoch + 1

############################ TRAIN ################################################################
losses = AverageMeter("loss")
accuracy = AverageMeter("accu")
correct = 0
total = 0
if use_cuda and len(device_ids)>1:
    model=nn.DataParallel(model, device_ids=device_ids)
elif use_cuda:
    model.cuda()
    print("now gpus are:" + str(os.environ['CUDA_VISIBLE_DEVICES']))
else:
    print("using cpu")
logger.info('start training!')
model.train()
for epoch in range(start_epoch, args.epoch+1): #epoch ???1?????? loss?????????
    for i, (images, labels) in enumerate(train_loader):
        if use_cuda:
            data,labels = images.cuda(), labels.cuda()
        #??????
        outputs, loss = model(images, labels) #todo ??????
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step()

        _, predicted = torch.max(outputs.cpu().data, 1)
        losses.update(loss.cpu().data.item())
        total += labels.size(0)
        correct += (predicted == labels).sum()
        accuracy.update(100 * correct / total)
        # todo accu loss????????????batch_size???
        if (i+1) % 2 == 0:
            logger.info('Epoch:%d/%d, Iter:%d/%d, Loss:%.4f, lr:%.4f'% \
                (epoch, args.epoch, i+1, len(train_dataset)//args.batch_size, losses.avg, optimizer.state_dict()['param_groups'][0]['lr']))
        if epoch % args.save_freq == 0:
            model_path = os.path.join(args.save_path, "model_epoch_{}.pth".format(epoch))
            state = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(), 'epoch': epoch}
            torch.save(state, model_path)

    if epoch % args.test_freq == 0:
        for i, (images, labels) in enumerate(test_loader):
            if use_cuda:
                data,labels = images.cuda(), labels.cuda()
            outputs = model(images)
            if (i+1) % 2 == 0:
                logger.info('Epoch:%d/%d, Iter:%d/%d'%(epoch, args.epoch, i+1, len(test_dataset)//args.batch_size))

# if __name__ == '__main__':
#     main()

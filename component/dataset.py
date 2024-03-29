from loguru import logger
import json
from torch.utils.data import Dataset
import numpy as np
import math


class PretrainDataset(Dataset):
    def __init__(self, file, tokenizer, max_seq_length, ignore_index=-100):
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length
        logger.info('Loading data: {}'.format(file))
        with open(file, 'r', encoding='utf8') as f:
            data_list = f.readlines()

        logger.info("there are {} data in dataset".format(len(data_list)))
        self.data_list = data_list

    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, index):
        data = self.data_list[index]
        text = json.loads(data)['text']
        return text


class EvalDataset(Dataset):
    """
    用于评测ppl
    """
    def __init__(self, file, tokenizer, max_seq_length, ignore_index=-100, sliding_window=256):
        self.tokenizer = tokenizer
        self.ignore_index = ignore_index
        self.pad_token_id = tokenizer.pad_token_id
        self.max_seq_length = max_seq_length
        logger.info('Loading data: {}'.format(file))
        token_list = np.memmap(file, dtype=np.uint16, mode='r').tolist()

        # 以滑动窗口截取评测数据
        eval_data_list = []
        for i in range(0, len(token_list), sliding_window):
            input_ids = token_list[i: i+max_seq_length]
            labels = token_list[i: i+max_seq_length]
            # padding
            padding_len = self.max_seq_length - len(input_ids)
            input_ids += [self.pad_token_id]*padding_len
            labels += [self.ignore_index]*padding_len
            eval_data_list.append({
                'input_ids': input_ids,
                'labels': labels
            })
        logger.info("there are {} data in eval dataset".format(len(eval_data_list)))
        self.data_list = eval_data_list

    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, index):
        data = self.data_list[index]
        return data


class VicunaSFTDataset(Dataset):

    def __init__(self, file, tokenizer, max_seq_length, ignore_index=-100):
        self.tokenizer = tokenizer
        self.ignore_index = ignore_index
        self.max_seq_length = max_seq_length
        self.pad_token_id = tokenizer.pad_token_id
        self.eos_token_id = tokenizer.eos_token_id
        logger.info('Loading data: {}'.format(file))
        with open(file, 'r', encoding='utf8') as f:
            data_list = f.readlines()

        logger.info("there are {} data in dataset".format(len(data_list)))
        self.data_list = data_list
        self.input_template = "A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions.\nUSER: {input}\nASSISTANT: "

    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, index):
        """
        沿袭Vicuna的的格式。
        A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions.
        USER: xxx
        ASSISTANT: xxx
        """
        data = self.data_list[index]
        data = json.loads(data)
        inputs = data['input'].strip()
        output = data['output'].strip()
        # 输入部分
        input_format = self.input_template.format(input=inputs)

        input_format_ids = self.tokenizer(input_format, add_special_tokens=False).input_ids
        output_ids = self.tokenizer(output, add_special_tokens=False).input_ids + [self.eos_token_id]

        input_ids = input_format_ids + output_ids
        labels = [self.ignore_index] * len(input_format_ids) + output_ids
        assert len(input_ids) == len(labels)

        # 对长度进行截断
        input_ids = input_ids[:self.max_seq_length]
        labels = labels[:self.max_seq_length]
        attention_mask = [1] * len(input_ids)
        # padding
        padding_len = self.max_seq_length - len(input_ids)
        input_ids += [self.pad_token_id] * padding_len
        labels += [self.ignore_index] * padding_len
        attention_mask += [0] * padding_len

        inputs = {
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'labels': labels
        }
        return inputs


class LlamaSFTDataset(Dataset):
    def __init__(self, file, tokenizer, max_seq_length, ignore_index=-100):
        self.tokenizer = tokenizer
        self.ignore_index = ignore_index
        self.max_seq_length = max_seq_length
        self.pad_token_id = tokenizer.pad_token_id
        self.eos_token_id = tokenizer.eos_token_id
        logger.info('Loading data: {}'.format(file))
        with open(file, 'r', encoding='utf8') as f:
            data_list = f.readlines()

        logger.info("there are {} data in dataset".format(len(data_list)))
        self.data_list = data_list
        self.input_template = "You are a professional machine learning conference reviewer who reviews a given paper and considers 4 criteria: \
            ** importance and novelty **, ** potential reasons for acceptance **, ** potential reasons for rejection **, and ** suggestions for improvement **.\
                \n The given paper is as follows:\n{input}\n"
        self.out_template = "Review result:\n{output}\n"
        
        
    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, index):
        data = self.data_list[index]
        data = json.loads(data)
        input = data['input'].strip()
        output = data['output'].strip()
    
        #组装prmopt    
        input_format = self.input_template.format(input=input)
        output_format = self.out_template.format(output=output)
        #分词
        input_ids = self.tokenizer(input_format, add_special_tokens=False).input_ids
        output_ids = self.tokenizer(output_format, add_special_tokens=False).input_ids 
        
        input_len = len(input_ids)
        output_len = len(output_ids)
        total_len =  input_len + output_len
        #超长，需要cut, 预留一个给eos
        if total_len > self.max_seq_length - 1:
            #cut比例
            scale_size = total_len / (self.max_seq_length - 1)
            #print(f"Cut begin, input: {input_len}, output: {output_len}, total: {input_len + output_len}")
            input_ids = input_ids[:math.floor(input_len/scale_size)] 
            output_ids =  output_ids[:math.floor(output_len/scale_size)] 
        output_ids += [self.eos_token_id]
        #print(f"input: {len(input_ids)}, output: {len(output_ids)}, total: {len(input_ids) + len(output_ids)}")
        
        labels = [self.ignore_index] * len(input_ids) + output_ids
        input_ids = input_ids + output_ids
        
        assert len(input_ids) == len(labels)
        assert len(input_ids) <= self.max_seq_length
        attention_mask = [1] * len(input_ids)

    
        # padding
        padding_len = self.max_seq_length - len(input_ids)
        input_ids += [self.pad_token_id] * padding_len
        labels += [self.ignore_index] * padding_len
        attention_mask += [0] * padding_len

        inputs = {
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'labels': labels
        }
        return inputs
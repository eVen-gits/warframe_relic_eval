import json
import requests
import sys
#https://go.microsoft.com/fwlink/?LinkId=691126
#easy_install python-Levenshtein
from fuzzywuzzy import fuzz

def json_to_obj_list(json_list):
    obj_list = []
    for i in range(len(json_list)):
        obj_list.append(Json2Obj(json_list[i]))
    return obj_list

def init_data(relic_list, item_list):
    keys = [item.item_name for item in item_list]
    item_dict = dict(zip(keys, item_list))

    n = len(relic_list)
    count = 0
    for relic in relic_list:
        for i, reward in enumerate(relic.rewards):
            if reward.itemName == 'Forma Blueprint':
                continue
                #TODO
                #del relic.rewards[i]
            item_name = reward.itemName.replace(' Blueprint', '')

            if reward.itemName in item_dict.keys():
                relic.rewards[i].__dict__ = {**reward.__dict__, **item_dict.get(reward.itemName).__dict__}
            elif item_name in item_dict.keys():
                relic.rewards[i].__dict__ = {**reward.__dict__, **item_dict.get(item_name).__dict__}
            else:

                for j, item in enumerate(item_list):
                    if fuzz.token_set_ratio(item.item_name, reward.itemName) == 100:
                        relic.rewards[i].__dict__ = {**reward.__dict__, **item.__dict__}
                        item = None
                        break
                if item:
                    print('Failed to find match for', reward.itemName)
        count = count+1
        sys.stdout.write("\rInitializing {:.2f}%".format(100*count/n))
        sys.stdout.flush()

    print(' ... Done!')

class Json2Obj:
    def __init__(self, json):
        """Constructor accepts json string as an argument.
        """
        self.__dict__ = json
        for i in self.__dict__.keys():
            child = self.__dict__[i]
            if isinstance(child, dict):
                if len(child) > 0:
                    self.__dict__[i] = Json2Obj(child)
            elif isinstance(child, list):
                for i in range(len(child)):
                    child[i] = Json2Obj(child[i])

if __name__ == '__main__':
    client = requests.session()
    relic_list = json_to_obj_list(
        json.loads(client.get(
            'https://drops.warframestat.us/data/relics.json').text)['relics'])
    item_list = json_to_obj_list(
        json.loads(client.get(
            'https://api.warframe.market/v1/items').text)['payload']['items']['en'])

    init_data(relic_list, item_list)

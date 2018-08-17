import json
import requests
import sys
import types
import csv
#https://go.microsoft.com/fwlink/?LinkId=691126
#easy_install python-Levenshtein
from fuzzywuzzy import fuzz
from ratelimit import limits, sleep_and_retry

DEBUG = True

drop_chance = {
    'quality': {
        'intact': {
            'common': 0.76/3,
            'uncommon': 0.11,
            'rare': 0.02
        },
        'exceptional': {
            'common': 0.7/3,
            'uncommon': 0.13,
            'rare': 0.04
        },
        'flawless': {
            'common': 0.2,
            'uncommon': 0.17,
            'rare': 0.06
        },
        'radiant': {
            'common': 1/6,
            'uncommon': 0.2,
            'rare': 0.2
        }
    }
}

relic_tiers = {
    'Lith',
    'Meso',
    'Neo',
    'Axi'
}

def median(lst):
    n = len(lst)
    if n < 1:
            return None
    if n % 2 == 1:
            return sorted(lst)[n//2]
    else:
            return sum(sorted(lst)[n//2-1:n//2+1])/2.0

@sleep_and_retry
@limits(calls=3, period=1.5)
def call_api(url):
    response = client.get(url)
    if response.status_code != 200:
        raise Exception('API response: {}'.format(response.status_code))
    return response

def json_to_obj_list(json_list):
    obj_list = []
    for i in range(len(json_list)):
        obj_list.append(Json2Obj(json_list[i]))
    return obj_list

def item_value(self):
    if self.itemName == 'Forma Blueprint':
        return 0
    if not self._value:
        url = "https://api.warframe.market/v1/items/{0}/orders".format(self.url_name)

        orders = [order['platinum'] for order in json.loads(call_api(url).text)['payload']['orders'] if order['order_type'] == 'sell' and order['user']['status'] == 'ingame']

        self._value = median(orders)
    return float(self._value)

def relic_value(self):
    val = 0
    for reward in self.rewards:
        val = val +  reward.chance/100 * reward.item_value()

    return val

def init_data(relic_list, item_list):
    keys = [item.item_name for item in item_list]
    item_dict = dict(zip(keys, item_list))

    relic_dict = dict()
    for tier in relic_tiers:
        relic_dict[tier] = dict()

    n = len(relic_list)
    count = 0

    for relic in relic_list:
        for i, reward in enumerate(relic.rewards):
            if reward.itemName == 'Forma Blueprint':
                match = reward
            else:
                item_name = reward.itemName.replace(' Blueprint', '')

                if reward.itemName in item_dict.keys():
                    match = item_dict.get(reward.itemName)
                    relic.rewards[i] = match
                    relic.rewards[i].__dict__ = {**reward.__dict__, **match.__dict__}
                elif item_name in item_dict.keys():
                    match = item_dict.get(item_name)
                    relic.rewards[i] = match
                    relic.rewards[i].__dict__ = {**reward.__dict__, **match.__dict__}
                else:
                    for j, item in enumerate(item_list):
                        if fuzz.token_set_ratio(item.item_name, reward.itemName) == 100:
                            relic.rewards[i] = item
                            relic.rewards[i].__dict__ = {**reward.__dict__, **item.__dict__}
                            match = item
                            break
                if not match:
                    raise KeyError('Failed to find match for', reward.itemName)

            #Init value cache field
            match._value = None
            match.item_value = types.MethodType(item_value, match)

        relic.relic_value = types.MethodType(relic_value, relic)

        if relic.relicName not in relic_dict[relic.tier]:
            relic_dict[relic.tier][relic.relicName] = dict()

        relic_dict[relic.tier][relic.relicName][relic.state] = relic

        count = count+1
        sys.stdout.write("\rInitializing {:.2f}%".format(100*count/n))
        sys.stdout.flush()

    print(' ... Done!')
    return relic_dict, item_dict

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
        json.loads(
            call_api(
                'https://drops.warframestat.us/data/relics.json'
            ).text
        )['relics']
    )

    item_list = json_to_obj_list(
        json.loads(
            call_api(
                'https://api.warframe.market/v1/items'
            ).text
        )['payload']['items']['en']
    )

    relic_dict, item_dict = init_data(relic_list, item_list)

    csvfile = open('export.csv', 'w', newline='', encoding='utf-8')
    filewriter = csv.writer(csvfile, delimiter=',')


    rows = 0
    for r_era in relic_dict.values():
        for r_name in r_era.values():
            for r in r_name.values():
                #if rows > 10:
                #    break
                print(r.tier, r.relicName, r.state, r.relic_value())
                csvrow = [r.tier, r.relicName, r.state, r.relic_value()]
                for drop in sorted(r.rewards, key=lambda el: el.item_value()):
                    csvrow += [drop.itemName, drop.item_value()]
                filewriter.writerow(csvrow)
                #rows = rows+1
    csvfile.close()
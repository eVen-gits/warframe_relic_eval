import json
import requests
import sys
import types
import csv
#https://go.microsoft.com/fwlink/?LinkId=691126
#easy_install python-Levenshtein
from fuzzywuzzy import fuzz
from ratelimit import limits, sleep_and_retry

refinement_levels = {
    'Intact': 0,
    'Exceptional': 25,
    'Flawless': 50,
    'Radiant': 100
}

relic_tiers = [
    'Lith',
    'Meso',
    'Neo',
    'Axi'
]

def median(lst):
    n = len(lst)
    if n < 1:
            return None
    if n % 2 == 1:
            return sorted(lst)[n//2]
    else:
            return sum(sorted(lst)[n//2-1:n//2+1])/2.0

@sleep_and_retry
@limits(calls=3, period=2)
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

def make_dropped_relic_set(mission_drops, cetus_drops, solaris_drops):
    drop_relic_set = set()

    for planet in mission_drops.values():
        for node in planet.values():
            rewards = node['rewards']
            if isinstance(rewards, dict):
                for rot in rewards.values():
                    for item in rot:
                        if fuzz.token_set_ratio(item['itemName'], "Relic") == 100:
                            drop_relic_set.add(item['itemName'])
            else:
                for item in rewards:
                   if fuzz.token_set_ratio(item['itemName'], "Relic") == 100:
                        drop_relic_set.add(item['itemName'])
    
    for bounty in cetus_drops:
        for rot in bounty['rewards'].values():
            for item in rot:
                if fuzz.token_set_ratio(item['itemName'], "Relic") == 100:
                    drop_relic_set.add(item['itemName'])
    
    for bounty in solaris_drops:
        for rot in bounty['rewards'].values():
            for item in rot:
                if fuzz.token_set_ratio(item['itemName'], "Relic") == 100:
                    drop_relic_set.add(item['itemName'])
    
    return drop_relic_set

def item_value(self):
    if not hasattr(self, 'url_name'):
        return 0
    if not self._value:
        url = "https://api.warframe.market/v1/items/{0}/orders".format(self.url_name)

        orders = [order['platinum'] for order in json.loads(call_api(url).text)['payload']['orders'] if order['order_type'] == 'sell' and order['user']['status'] == 'ingame']

        self._value = median(orders)
    return float(self._value)

def relic_value(self):
    val = 0
    for reward in sorted(self.rewards, key=lambda el: el.chance):
        val = val +  reward.chance/100 * reward.item_value()
    return val

def init_data(relic_list, item_list, dropped_relics):
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
                    relic.rewards[i].url_name = match.url_name
                elif item_name in item_dict.keys():
                    match = item_dict.get(item_name)
                    relic.rewards[i].url_name = match.url_name
                else:
                    for j, item in enumerate(item_list):
                        if fuzz.token_set_ratio(item.item_name, reward.itemName) == 100:
                            relic.rewards[i].url_name = item.url_name
                            match = item
                            break
                if not match:
                    raise KeyError('Failed to find match for', reward.itemName)

            #Init value cache field
            match._value = None
            match.item_value = types.MethodType(item_value, match)
            relic.rewards[i].item_value = match.item_value

        relic.vaulted = True
        for drop_relic in dropped_relics:
            if fuzz.token_set_ratio(drop_relic, "{0} {1}".format(relic.tier, relic.relicName)) == 100:
                relic.vaulted = False
                break
            
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
        )['payload']['items']
    )
    
    mission_drops = json.loads(
        call_api(
            'https://drops.warframestat.us/data/missionRewards.json'
        ).text
    )['missionRewards']
    cetus_drops = json.loads(
        call_api(
            'https://drops.warframestat.us/data/cetusBountyRewards.json'
        ).text
    )['cetusBountyRewards']
    solaris_drops = json.loads(
        call_api(
            'https://drops.warframestat.us/data/solarisBountyRewards.json'
        ).text
    )['solarisBountyRewards']
    
    dropped_relics = make_dropped_relic_set(mission_drops, cetus_drops, solaris_drops)

    relic_dict, item_dict = init_data(relic_list, item_list, dropped_relics)

    csv_values = open('export.csv', 'w', newline='', encoding='utf-8')
    values_writer = csv.writer(csv_values, delimiter=',')

    csv_refinement = open('refinement.csv', 'w', newline='', encoding='utf-8')
    refinement_writer = csv.writer(csv_refinement, delimiter=',')

    rows = 0
    values_writer.writerow(['Era', 'Relic', 'Vaulted',] + list(refinement_levels.keys()))
    refinement_writer.writerow(['Era', 'Relic', 'Vaulted',] + list(refinement_levels.keys())[1:])
    for k_era, v_era in relic_dict.items():
        for k_name, v_name in v_era.items():
            #if rows > 10:
            #    break
            value_row = [k_era, k_name, list(v_name.values())[0].vaulted]
            refinement_row = [k_era, k_name, list(v_name.values())[0].vaulted]
            print(k_era, k_name)
            first = prev = None
            for r in v_name.values():
                relic_value = r.relic_value()
                value_row += [relic_value]
                if not first:
                    first = relic_value
                if prev:
                    gain = relic_value - prev
                    gpp = gain/refinement_levels[r.state]
                    refinement_row += [gpp]
                prev = relic_value

            for drop in sorted(v_name['Intact'].rewards, key=lambda el: el.item_value()):
                value_row += [drop.itemName, drop.item_value()]

            values_writer.writerow(value_row)
            refinement_writer.writerow(refinement_row)
            #rows = rows+1
    csv_values.close()
    csv_refinement.close()

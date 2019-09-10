"""
PaStA - Patch Stack Analysis

Copyright (c) BMW Cat It, 2019

Author:
  Sebastian Duda <sebastian.duda@fau.de>

This work is licensed under the terms of the GNU GPL, version 2. See
the COPYING file in the top-level directory.
"""

import datetime
from logging import getLogger
import math
import matplotlib.colors as nrm
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import pickle
import re
import sys
from tqdm import tqdm
import tikzplotlib

log = getLogger(__name__[-15:])

d_resources = './resources/linux/'
f_prefix = 'eval_'
f_suffix = '.pkl'

patch_data = None
author_data = None
subsystem_data = None
corr = []
show = True


def plot_total_rejected_ignored(data, x, ax):
    data.plot(x=x, y='total', ax=ax)
    data.plot(x=x, y='rejected', ax=ax)
    data.plot(x=x, y='ignored', ax=ax)


def corr_rejected_ignored(data):
    tmp1 = data.corr('pearson')
    corr.append({
        'tot_rej': tmp1['total']['rejected'],
        'tot_ign': tmp1['total']['ignored'],
        'rej_ign': tmp1['rejected']['ignored']
    })


def plot_and_corr(data, x, ax, from_index=False):
    global corr

    if from_index:
        data = data.reset_index()
    plot_total_rejected_ignored(data, x, ax)
    corr_rejected_ignored(data)


def display_and_save_plot(name):
    global show
    plt.savefig('plots/' + name + '.svg')
    plt.savefig('plots/' + name + '.png', dpi=600)
    #tikzplotlib.save('plots' + name + ".tex")
    if show:
        plt.show()
    log.info('Plotted ' + name)


def normalize(data, max, args, by):
    factor = max / data[by]
    for item in args:
        data[item] = data[item] * factor
    return data


def p_by_rc():
    data = []
    for i in range(0, 11):
        data.append({'rc': i, 'total': 0, 'rejected': 0, 'ignored': 0})

    grp = patch_data.groupby(['rcv'])
    total = grp.count()['id']

    data = pd.DataFrame()
    data['kvs'] = patch_data[['rcv', 'kernel version']].groupby(['rcv']).nunique()['kernel version']
    data['total'] = total
    data['rejected'] = total - grp.sum()['upstream']
    data['ignored'] = grp.sum()['ignored']
    data.sort_index(inplace=True)
    data.reset_index(inplace=True)

    # Normalize odd rcvs
    data = data.apply(normalize, axis=1, args=(data['kvs'].max(), ['total', 'rejected', 'ignored', 'kvs'], 'kvs'))

    ax = plt.gca()
    ax.set_yscale('log')

    plot_total_rejected_ignored(data, 'rcv', ax)
    display_and_save_plot('by_rc')

    data['rejected/total'] = data['rejected'] / data['total']
    data['ignored/total'] = data['ignored'] / data['total']

    data.plot(x='rcv', y='rejected/total')
    display_and_save_plot('by_rc_r_ratio')

    data.plot(x='rcv', y='ignored/total')
    display_and_save_plot('by_rc_i_ratio')


def p_by_rc_v():
    ax = plt.gca()
    ax.set_yscale('log')

    g = patch_data.groupby(['kernel version', 'rcv'])
    d1 = g.sum()
    d2 = g.count()

    total = d2['id']
    rejected = total - d1['upstream']
    ignored = d1['ignored']

    series = {'total': total, 'rejected': rejected, 'ignored': ignored}
    frame = pd.DataFrame(series)
    frame.groupby(['kernel version']).apply(lambda x: plot_and_corr(x, 'rcv', ax, from_index=True))

    frame.reset_index(inplace=True)
    frame.sort_values(['rcv'], inplace=True)

    # frame['rejected/total'] = frame['rejected'] / frame['total']
    # frame.boxplot(by='rcv', column='rejected/total')
    # display_and_save_plot('by_rc_r_box')

    frame['ignored/total'] = frame['ignored'] / frame['total']
    ax = frame.boxplot(by='rcv', column='ignored/total')
    ax.set_xticklabels(
        ['MW', 'rc1..', 'rc2..', 'rc3..', 'rc4..', 'rc5..', 'rc6..', 'rc7..', 'rc8..', 'rc9..', 'rc10..'])
    ax.set_ylabel('Ratio Ignored/Total')
    ax.set_title('')
    ax.get_figure().suptitle('')
    display_and_save_plot('by_rc_i_box')
    am = 0
    am = frame['ignored/total'].mean()
    print('AM: ' + str(am))

    # global corr
    # ax.set_yscale('linear')
    # corr = pd.DataFrame(corr)
    # corr.boxplot()
    # display_and_save_plot('by_rc_v_bp')


def _smooth(data, column, x):
    for i in range(0, len(data.index)):
        avg = data[column].iloc[i]
        count = 1
        for j in range(1, x + 1):
            if i + j < len(data.index):
                avg += data[column].iloc[i + j]
                count += 1
            elif i - j > 0:
                avg += data[column].iloc[i - j]
                count += 1
        data[column].iloc[i] = avg / count


def p_by_time():
    global patch_data
    day = patch_data['time'].apply(lambda x: datetime.datetime(year=x.year, month=x.month, day=x.day))
    patch_data['day'] = day - pd.to_timedelta(day.dt.dayofweek, unit='d')

    patch_data = patch_data[patch_data['day'].apply(lambda x: x > patch_data['day'].min())]
    patch_data = patch_data[patch_data['day'].apply(lambda x: x < patch_data['day'].max())]

    grouped = patch_data.groupby(['day'])
    total = grouped.count()['id']
    rejected = total - grouped.sum()['upstream']
    ignored = grouped.sum()['ignored']

    result_frame = pd.DataFrame()
    result_frame['total'] = total
    result_frame['rejected'] = rejected
    result_frame['ignored'] = ignored

    ax = plt.gca()
    ax.set_yscale('log')
    ax.set_ylabel('Patches per Week')
    ax.set_xlabel('')
    result_frame.plot.line(x='day', y=['total', 'ignored'], ax=ax)
    display_and_save_plot('by_time')

    # Plot Scatterplot with regression line Ignored
    ax = plt.gca()
    result_frame.plot.scatter(x='total', y='ignored', ax=ax)

    fit_fn = np.poly1d(np.polyfit(result_frame['total'], result_frame['ignored'], 1))
    result_frame['reg_ign'] = result_frame['total'].apply(lambda x: fit_fn(x))
    result_frame.plot(x='total', y='reg_ign', ax=ax)

    display_and_save_plot('by_time_ign_scat')
    print('regression of ignored/total (scat): ' + str(fit_fn))

    # Plot Scatterplot with regression line Rejected
    ax = plt.gca()
    result_frame.plot.scatter(x='total', y='rejected', ax=ax)

    fit_fn = np.poly1d(np.polyfit(result_frame['total'], result_frame['rejected'], 1))
    result_frame['reg_rej'] = result_frame['total'].apply(lambda x: fit_fn(x))
    result_frame.plot(x='total', y='reg_rej', ax=ax)

    display_and_save_plot('by_time_rej_scat')

    tmp = result_frame.corr('pearson')
    print('Total/Rejected: ' + str(tmp['total']['rejected']))
    print('Total/Ignored: ' + str(tmp['total']['ignored']))
    print('Rejected/Ignored: ' + str(tmp['rejected']['ignored']))

    result_frame = pd.DataFrame()
    result_frame['ignored/total'] = ignored / total
    result_frame.reset_index(inplace=True)
    _smooth(result_frame, 'ignored/total', 3)

    fit_fn = np.poly1d(np.polyfit(result_frame.index, result_frame['ignored/total'], 1))
    result_frame['index'] = pd.Series(result_frame.index)
    result_frame['regression'] = result_frame['index'].apply(lambda x: fit_fn(x))

    ax = result_frame.plot.line(x='day', y=['ignored/total', 'regression'])

    display_and_save_plot('by_time_ratio_ign')
    print('regression of ignored/total (line): ' + str(fit_fn))

    # result_frame['rejected/total'] = rejected/total
    # _smooth(result_frame, 'rejected/total', 3)

    # result_frame.plot.line()
    # display_and_save_plot('by_time_ratio')
    pass


def _plot_groups_old(data):
    group = data['group'][0]
    data['from'] = data['from'].apply(lambda x: 2 * math.sqrt(x) + 10)

    data.plot.scatter(x='total', y='rejected', s=data['from'])
    display_and_save_plot('total_rej_abs_' + str(group))

    data.plot.scatter(x='total', y='r_ratio', s=data['from'])
    display_and_save_plot('total_rej_rel_' + str(group))

    data.plot.scatter(x='total', y='ignored', s=data['from'])
    display_and_save_plot('total_ign_abs_' + str(group))

    data.plot.scatter(x='total', y='i_ratio', s=data['from'])
    display_and_save_plot('total_ign_rel_' + str(group))

    return data


def _plot_groups(data, dim, y_label=None, group=None, plot_label=None):
    if not group:
        group = data['group'][data.index[0]]
    cmap = plt.get_cmap('jet').reversed()
    norm = nrm.LogNorm(vmin=1, vmax=data['from'].max())

    ax = data.plot.scatter(x='total', y=dim, c='from', colormap=cmap, norm=norm, s=1)
    if y_label:
        ax.set_ylabel(y_label)

    if plot_label:
        ax.set_title(plot_label)

    display_and_save_plot('total_' + dim + str(group))


borders = [100, 4000]


def a_total_rej_ign():
    global author_data
    authors = []
    for author, data in author_data.items():
        tot = 0
        ups = 0
        ign = 0

        for patch in data:
            tot += 1
            if patch['ignored']:
                ign += 1
            if patch['upstream']:
                ups += 1

        authors.append({
            'from': author,
            'total': tot,
            'ignored': ign,
            'i_ratio': ign / tot,
            'rejected': tot - ups,
            'r_ratio': (tot - ups) / tot
        })

        if tot >= borders[1] or ign > 200:
            print('Author ' + author[0] + ' ' + author[1] + ' has ' + str(tot) + ' totals, ' + str(tot - ups) + ' rejected, and ' + str(
                ign) + ' ignored patches.')

    authors = pd.DataFrame(authors)
    r_data = authors[['total', 'rejected', 'r_ratio', 'from']].groupby(
        ['total', 'rejected', 'r_ratio']).count().reset_index()
    i_data = authors[['total', 'ignored', 'i_ratio', 'from']].groupby(
        ['total', 'ignored', 'i_ratio']).count().reset_index()
    r_data['group'] = r_data['total'].apply(lambda x: 0 if x < borders[0] else 1 if x < borders[1] else 2)
    i_data['group'] = i_data['total'].apply(lambda x: 0 if x < borders[0] else 1 if x < borders[1] else 2)

    p_groups = r_data.groupby(by=['group'])
    r_groups = dict()
    for group, data in p_groups:
        r_groups[group] = data

    p_groups = i_data.groupby(by=['group'])
    i_groups = dict()
    for group, data in p_groups:
        i_groups[group] = data

    if r_groups[0]:
        _plot_groups(r_groups[0], 'rejected', 'rejected', 0)
        _plot_groups(r_groups[0], 'r_ratio', 'ratio rejected/total', 0)

    if i_groups[0]:
        _plot_groups(i_groups[0], 'ignored', 'ignored', 0)
        _plot_groups(i_groups[0], 'i_ratio', 'ratio ignored/total', 0)

    _plot_groups(pd.concat([r_groups[0], r_groups[1]]), 'rejected', 'rejected', '0-1')
    _plot_groups(pd.concat([r_groups[0], r_groups[1]]), 'r_ratio', 'ratio rejected/total', '0-1')

    _plot_groups(pd.concat([i_groups[0], i_groups[1]]), 'ignored', 'ignored', '0-1')
    _plot_groups(pd.concat([i_groups[0], i_groups[1]]), 'i_ratio', 'ratio ignored/total', '0-1')

    print('regression of rejected: ' + str(np.poly1d(np.polyfit(r_data['total'], r_data['rejected'], 1))))
    print('regression of rejected ratio: ' + str(np.poly1d(np.polyfit(r_data['total'], r_data['r_ratio'], 1))))
    print('regression of ignored: ' + str(np.poly1d(np.polyfit(i_data['total'], i_data['ignored'], 1))))
    print('regression of ignored ratio: ' + str(np.poly1d(np.polyfit(i_data['total'], i_data['i_ratio'], 1))))


def build_data():
    print(' building…')
    global author_data
    global subsystem_data

    author_data = dict()
    subsystem_data = dict()

    for index, tline in patch_data.iterrows():
        line = tline.to_dict()
        try:
            author_data[line['from']].append(line)
        except KeyError:
            author_data[line['from']] = [line]
#        if line['subsystems'] is None:
#            continue
#        for subsystem in line['subsystems']:
#            try:
#                subsystem_data[subsystem].append(line)
#            except KeyError:
#                subsystem_data[subsystem] = [line]


def analysis_patches(config, prog, argv):
    global author_data
    global patch_data
    global subsystem_data

    _, clustering = config.load_cluster()
    clustering.optimize()

    log.info('Loading Data')

    load = pickle.load(open(d_resources + 'eval_characteristics.pkl', 'rb'))
    ignored_single = set()

    irrelevants = set()
    relevant = set()
    for patch, character in load.items():
        if not character.is_patch or not character.patches_linux or character.is_stable_review or \
                character.is_next or character.process_mail or character.is_from_bot:
            irrelevants.add(patch)
            continue
        relevant.add(patch)

    for patch in irrelevants:
        del load[patch]

    for patch, character in load.items():
        if not (character.is_upstream or character.has_foreign_response):
            ignored_single.add(patch)

    ignored_related = {patch for patch in ignored_single
                        if False not in [load[x].has_foreign_response == False
                                          for x in (clustering.get_downstream(patch) & relevant)]}

    data = []
    for patch, character in load.items():
        tag = character.linux_version
        rc = 'rc' in tag

        if rc:
            rc = re.search('-rc[0-9]+', tag).group()[3:]
            kv = re.search('v[0-9]+\.', tag).group() + '%02d' % int(re.search('\.[0-9]+', tag).group()[1:])
        else:
            rc = 0
            kv = re.search('v[0-9]+\.', tag).group() + '%02d' % (
                    int(re.search('\.[0-9]+', tag).group()[1:]) + 1)
        ignored = patch in ignored_related

        data.append({
            'id': patch,
            'from': character.mail_from,
            'kernel version': kv,
            'rcv': rc,
            'upstream': character.is_upstream,
            'ignored': ignored,
            'time': character.date
        })
    log.info('There are ' + str(len(irrelevants)) + ' irrelevant Mails.')
    patch_data = pd.DataFrame(data)

    # Clean Data
    # remove v2.* and v5.*
    patch_data.set_index('kernel version', inplace=True)
    patch_data = patch_data.filter(regex='^v[^25].*', axis=0)
    patch_data.reset_index(inplace=True)
    # Remove outlier
    pre_outlier = len(patch_data.index)
    '''
    patch_data = patch_data[patch_data['from'].apply(lambda x: not x in [
        # Total > 3500
        ('arnaldo carvalho de melo', 'acme@kernel.org'),
        ('jeff kirsher', 'jeffrey.t.kirsher@intel.com'),
        ('simon horman', 'horms+renesas@verge.net.au'),
        ('christoph hellwig', 'hch@lst.de'),
        ('marc zyngier', 'marc.zyngier@arm.com'),
        ('arnd bergmann', 'arnd@arndb.de'), # + rejected
        # Ignored > 200
        ('baole ni', 'baolex.ni@intel.com'),
        ('rickard strandqvist', 'rickard_strandqvist@spectrumdigital.se'),
        # Total + Rejected + Ignored
        ('sf markus elfring', 'elfring@users.sourceforge.net'),
        ('mark brown', 'broonie@kernel.org')
    ])]
    '''
    #patch_data = patch_data[patch_data['time'].apply(lambda x: x.year >= 2018)]

    post_outlier = len(patch_data.index)
    log.info(str(pre_outlier - post_outlier) + ' Patches were removed. (Outlier)')
    log.info(str(post_outlier) + ' Patches remain.')
    # Bool to int
    patch_data = patch_data.replace(True, 1)
    # rcv as int
    patch_data['rcv'] = patch_data['rcv'].apply((lambda x: int(x)))

    if os.path.isfile(d_resources + 'other_data.pkl') and False:
        author_data, subsystem_data = pickle.load(open(d_resources + 'other_data.pkl', 'rb'))
    else:
        build_data()
        pickle.dump((author_data, subsystem_data), open(d_resources + 'other_data.pkl', 'wb'))

    log.info(' → Done')

    #p_by_rc()
    p_by_rc_v()
    p_by_time()
    a_total_rej_ign()

# Copyright 2025 Dylan Montgomery
# Licensed under the Apache License, Version 2.0 (the "License");

# mycite_project/MSS_convention.py
# AUTHOR:   Dylan Montgomery
# VERSION:	10.04.04

class DnmcDtm:
    def __init__(self, layer_i: int, group_m: int, iteration_k: int, a: int, b: int):
        self.layer = layer_i
        self.group = group_m
        self.iteration = iteration_k
        self.reference = a
        self.magnitude = b
        self.id = [self.layer, self.group, self.iteration]
        
        # Global Variable used optionally
        self.mbrObjs[][] = []
    
    def ui_handle(self, mbrs):
        self.mbrObjs[self.app.ui_rows][self.app.ui_cols + 1] = []
        for mbr in mbrs:
            self.mbrObjs[0][mbr] = self.app.objects[mbrs[mbr]]

def bitInt(bits: list[int]) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | (b & 1)
    return v

def slice_every(bits: list[int], width: int) -> list[list[int]]:
    if width <= 0:
        return []
    out = []
    for i in range(0, len(bits) - (len(bits) % width), width):
        out.append(bits[i:i+width])
    return out

class MSS():
    def __init__(self):
        self.capture: list[int] = []
        
        self.index_a = []
        self.index_b = []
        self.index_c = []
        
        self.index_d = []
        self.index_g = []
        
        self.index_e = []
        self.index_s = []
        
        self.ssid_g = []
        
        self.flmnt_ssid = []

    def boot(self):
        with open('world.bin', 'rb') as f:
            raw = f.read()
        for byte in raw:
            for bitpos in range(7, -1, -1):
                self.capture.append((byte >> bitpos) & 1)
        
        n = len(self.capture)
        a_stp = 0

        while a_stp < n and self.capture[a_stp] == 1:
            a_stp += 1
        
        self.index_a = self.capture[:a_stp]
        adrs_sz = len(self.index_a) - 1

        self.index_b = self.capture[(a_stp+1):((2*a_stp)+1)]
        self.index_c = self.capture[((2*a_stp)+1):((3*a_stp)+1)]
        
        d_end = bitInt(self.index_c[:a_stp]) if a_stp > 0 else ((3*a_stp)+1)
        g_end = bitInt(self.index_c[a_stp:(2*a_stp)]) if a_stp > 0 else d_end
        e_beg = bitInt(self.index_c[(2*a_stp):(3*a_stp)]) if a_stp > 0 else g_end

        self.index_d = self.capture[((3*a_stp)+1):d_end]
        self.index_g = self.capture[d_end:g_end]
        self.index_e = self.capture[e_beg:e_beg]
        self.index_s = self.capture[e_beg:]

    @staticmethod
    def compute_index_d_adrss(index_d, adrs_sz):
        if adrs_sz <= 0:
            return []
        index_d_adrss = []
        start = 0
        while start + adrs_sz <= len(index_d):
            stop = start + adrs_sz
            index_d_adrss.append(bitInt(index_d[start:stop]))
            start = stop
        return index_d_adrss

    @staticmethod
    def compute_index_g_vls(index_g, index_d_adrss):
        index_g_vls = []
        prev = 0
        n = len(index_g)
        for stop in index_d_adrss:
            stop = min(stop, n)
            index_g_vls.append(bitInt(index_g[prev:stop]))
            prev = stop
        index_g_vls.append(bitInt(index_g[prev:n]))
        return index_g_vls

    def boot_load(self):
        adrs_sz = len(self.index_a) - 1
        index_d_adrss = self.compute_index_d_adrss(self.index_d, adrs_sz)
        index_g_vls   = self.compute_index_g_vls(self.index_g, index_d_adrss)
        pos = 0
        if len(index_g_vls) < 2:
            # Nothing to parse; leave defaults
            self.ssid_g = []
            self.flmnt_ssid = []
            return self.ssid_g, self.flmnt_ssid

        _sentinel_or_unused = index_g_vls[pos]; pos += 1
        L = index_g_vls[pos] if pos < len(index_g_vls) else 0
        pos += 1
        L = max(0, L)

        # group counts per layer
        group_counts = []
        for _ in range(L):
            if pos >= len(index_g_vls):
                group_counts.append(0)
            else:
                group_counts.append(max(0, index_g_vls[pos]))
            pos += 1

        # iteration counts laid out layer-by-layer
        iter_counts = []
        for gi in group_counts:
            counts_for_layer = []
            for _ in range(gi):
                if pos >= len(index_g_vls):
                    counts_for_layer.append(0)
                else:
                    counts_for_layer.append(max(0, index_g_vls[pos]))
                pos += 1
            iter_counts.append(counts_for_layer)

        # Now parse the payload pairs (a,b) for each iteration, in order
        ssid_g_nested: list[list[list[list[int]]]] = []  # [layer][group][iteration] -> [a,b]
        flmnt: list[DnmcDtm] = []

        for layer_i in range(L):
            layer_list: list[list[list[int]]] = []
            groups_in_layer = group_counts[layer_i] if layer_i < len(group_counts) else 0

            for group_m in range(groups_in_layer):
                num_iters = iter_counts[layer_i][group_m] if (layer_i < len(iter_counts) and group_m < len(iter_counts[layer_i])) else 0
                iters_list: list[list[int]] = []

                for iteration_k in range(num_iters):
                    # Guard against running out of data
                    if pos + 1 >= len(index_g_vls):
                        # If data is short, pad zeros
                        a = 0
                        b = 0
                    else:
                        a = index_g_vls[pos]
                        b = index_g_vls[pos + 1]
                    pos += 2

                    iters_list.append([a, b])
                    flmnt.append(DnmcDtm(layer_i=layer_i + 1,
                                         group_m=group_m + 1,
                                         iteration_k=iteration_k + 1,
                                         a=a, b=b))
                layer_list.append(iters_list)
            ssid_g_nested.append(layer_list)

        # Store results on the instance
        self.ssid_g = ssid_g_nested
        self.flmnt_ssid = flmnt
    
            # Return both so your main program can directly receive them
        return self.ssid_g, self.flmnt_ssid
# MODIFIED:	2025-10-19
# VERSION:	10.04.01

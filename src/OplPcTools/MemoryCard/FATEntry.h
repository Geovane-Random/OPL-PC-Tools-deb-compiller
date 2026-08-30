/***********************************************************************************************
 * Copyright © 2017-2026 Sergey Smolyannikov aka brainstream                                   *
 *                                                                                             *
 * This file is part of the OPL PC Tools project, the graphical PC tools for Open PS2 Loader.  *
 *                                                                                             *
 * OPL PC Tools is free software: you can redistribute it and/or modify it under the terms of  *
 * the GNU General Public License as published by the Free Software Foundation,                *
 * either version 3 of the License, or (at your option) any later version.                     *
 *                                                                                             *
 * OPL PC Tools is distributed in the hope that it will be useful,  but WITHOUT ANY WARRANTY;  *
 * without even the implied warranty of  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  *
 * See the GNU General Public License for more details.                                        *
 *                                                                                             *
 * You should have received a copy of the GNU General Public License along with OPL PC Tools   *
 * If not, see <http://www.gnu.org/licenses/>.                                                 *
 *                                                                                             *
 ***********************************************************************************************/

#pragma once

#include <cstdint>

namespace OplPcTools {
namespace MemoryCard {

enum FATEntryFlag : uint8_t
{
    FAT_FREE = 0x7F,
    FAT_EOF = 0xFF,
    FAT_POINTER = 0x80
};

struct FATEntry
{
    uint8_t data[4];

    static constexpr FATEntry free()
    {
        return { 0xFF, 0xFF, 0xFF, FAT_FREE };
    }

    static constexpr FATEntry endOfFile()
    {
        return { 0xFF, 0xFF, 0xFF, FAT_EOF };
    }

    static constexpr FATEntry pointer(uint32_t _cluster)
    {
        return
        {
            static_cast<uint8_t>(_cluster),
            static_cast<uint8_t>(_cluster >> 8),
            static_cast<uint8_t>(_cluster >> 16),
            FAT_POINTER
        };
    }

    constexpr uint32_t cluster() const
    {
        return static_cast<uint32_t>(data[0]) |
               (static_cast<uint32_t>(data[1]) << 8) |
               (static_cast<uint32_t>(data[2]) << 16);
    }

    constexpr bool isFree() const
    {
        return data[3] == FAT_FREE;
    }

    constexpr bool isEndOfFile() const
    {
        return data[3] == FAT_EOF;
    }

    constexpr bool isPointer() const
    {
        return data[3] == FAT_POINTER;
    }
};

static_assert(sizeof(FATEntry) == 4, "A memory-card FAT entry must occupy exactly four bytes");

} // namespace MemoryCard
} // namespace OplPcTools

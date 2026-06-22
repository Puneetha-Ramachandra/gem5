# micro_elf.py: Shared ELF Generator and Patcher for gem5-micro
# Provides utilities to generate spin executables and patch compiled binaries
# for synthetic micro-op injection without requiring native cross-compilers.

import os
import struct

# Constants
RISCV_NOP = 0x00000013  # addi x0, x0, 0
RISCV_JMP = 0x0000006f  # jal x0, 0 (infinite loop)

X86_NOP   = 0x90        # nop
X86_JMP   = b'\xeb\xfe' # jmp $ (jump-to-self infinite loop)

def make_spin_elf(path, arch='riscv', spin_addr=0x10000, nop_addr=None):
    """Write a minimal ELF64 binary with two PT_LOAD segments:
      - segment 0: spin loop (infinite loop)
      - segment 1: NOP page (synthetic PC landing zone for injected micro-ops)
      
    Returns:
      (spin_addr, nop_addr)
    """
    if arch == 'riscv':
        machine = 0xF3      # EM_RISCV
        spin_code = struct.pack('<I', RISCV_JMP) * 1024
        nop_code  = struct.pack('<I', RISCV_NOP) * 1024
        align = 0x1000
    elif arch == 'x86':
        machine = 0x3E      # EM_X86_64
        # Repeat jump-to-self pattern to fill 4KB, or pad it
        spin_code = X86_JMP * 2048
        nop_code  = bytes([X86_NOP]) * 4096
        align = 0x1000
    else:
        raise ValueError(f"Unsupported architecture: {arch}")

    if nop_addr is None:
        # Align nop_addr to the next page boundary after spin segment
        nop_addr = ((spin_addr + len(spin_code) - 1) // align + 1) * align

    # ELF64 Ident
    e_ident = b'\x7fELF\x02\x01\x01\x00' + b'\x00' * 8
    
    # ELF64 Header
    # e_type=2 (EXEC), e_machine=machine, e_version=1, e_entry=spin_addr
    # e_phoff=64, e_shoff=0, e_flags=0, e_ehsize=64, e_phentsize=56, e_phnum=2
    elf_hdr = struct.pack('<HHIQQQIHHHHHH',
        2, machine, 1, spin_addr,
        64,       # e_phoff
        0,        # e_shoff
        0,        # e_flags
        64,       # e_ehsize
        56,       # e_phentsize
        2,        # e_phnum
        0, 0, 0   # e_shentsize, e_shnum, e_shstrndx
    )

    # Segment 0 Program Header (Spin Code)
    spin_off = 64 + 56 * 2  # data starts immediately after headers
    ph0 = struct.pack('<IIQQQQQQ',
        1, 5,               # p_type=1 (PT_LOAD), p_flags=5 (PF_R|PF_X)
        spin_off,           # p_offset
        spin_addr,          # p_vaddr
        spin_addr,          # p_paddr
        len(spin_code),     # p_filesz
        len(spin_code),     # p_memsz
        align               # p_align
    )

    # Segment 1 Program Header (NOP Page)
    nop_off = spin_off + len(spin_code)
    ph1 = struct.pack('<IIQQQQQQ',
        1, 5,               # p_type=1 (PT_LOAD), p_flags=5 (PF_R|PF_X)
        nop_off,            # p_offset
        nop_addr,           # p_vaddr
        nop_addr,           # p_paddr
        len(nop_code),      # p_filesz
        len(nop_code),      # p_memsz
        align               # p_align
    )

    with open(path, 'wb') as f:
        f.write(e_ident + elf_hdr + ph0 + ph1 + spin_code + nop_code)
    
    os.chmod(path, 0o755)
    return spin_addr, nop_addr


def patch_elf_for_microisa(src_path, dst_path, arch='riscv', nop_addr=None):
    """Read an existing ELF64 executable, append a new loadable segment
    containing NOPs (synthetic PC base), and write it to dst_path.
    
    Returns:
      (entry_addr, nop_addr)
    """
    with open(src_path, 'rb') as f:
        elf_data = bytearray(f.read())

    if len(elf_data) < 64:
        raise ValueError("Invalid ELF: file too small")

    # Verify ELF ident
    if elf_data[:4] != b'\x7fELF':
        raise ValueError("Invalid ELF: missing magic header")

    # Read basic ELF headers
    e_entry = struct.unpack('<Q', elf_data[24:32])[0]
    e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
    e_phnum = struct.unpack('<H', elf_data[56:58])[0]
    e_phentsize = struct.unpack('<H', elf_data[54:56])[0]

    if e_phentsize != 56:
        raise ValueError(f"Invalid ELF: unexpected ph entry size {e_phentsize}")

    # Parse existing program headers to find max virtual address and setup alignment
    max_addr = 0
    program_headers = []
    for i in range(e_phnum):
        offset = e_phoff + i * 56
        ph = elf_data[offset:offset+56]
        p_type, p_flags = struct.unpack('<II', ph[:8])
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack('<QQQQQQ', ph[8:])
        
        if p_type == 1: # PT_LOAD
            max_addr = max(max_addr, p_vaddr + p_memsz)
            program_headers.append((p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align))

    align = 0x1000
    if nop_addr is None:
        # Align to the next page boundary
        nop_addr = (max_addr + align - 1) & ~(align - 1)

    # Prepare NOP instructions
    if arch == 'riscv':
        nop_code = struct.pack('<I', RISCV_NOP) * 1024
    elif arch == 'x86':
        nop_code = bytes([X86_NOP]) * 4096
    else:
        raise ValueError(f"Unsupported architecture: {arch}")

    # To add a new program header cleanly without overwriting existing sections,
    # we append the new NOP code first.
    nop_offset_in_file = len(elf_data)
    elf_data.extend(nop_code)

    # Create the new program header
    new_ph = struct.pack('<IIQQQQQQ',
        1, 5,                       # p_type=1 (PT_LOAD), p_flags=5 (PF_R|PF_X)
        nop_offset_in_file,         # p_offset
        nop_addr,                   # p_vaddr
        nop_addr,                   # p_paddr
        len(nop_code),              # p_filesz
        len(nop_code),              # p_memsz
        align                       # p_align
    )

    # Now we append the updated program header table to the end of the file
    new_ph_offset_in_file = len(elf_data)
    
    # Write existing program headers
    for i in range(e_phnum):
        offset = e_phoff + i * 56
        elf_data.extend(elf_data[offset:offset+56])
        
    # Write the new program header
    elf_data.extend(new_ph)

    # Update ELF Header at the start of the file:
    # 1. Update e_phoff to point to the new location at the end of the file
    elf_data[32:40] = struct.pack('<Q', new_ph_offset_in_file)
    # 2. Increment e_phnum by 1
    elf_data[56:58] = struct.pack('<H', e_phnum + 1)

    with open(dst_path, 'wb') as f:
        f.write(elf_data)
        
    os.chmod(dst_path, 0o755)
    return e_entry, nop_addr

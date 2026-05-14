# 指定CMake的最低版本要求
cmake_minimum_required(VERSION 3.10)

# 定义项目名称和语言
project(demo-ccsds C)

# 设置C语言标准为C11
set(CMAKE_C_STANDARD 11)

# 添加可执行文件目标，并包含所有需要的.c源文件
add_executable(ccsds_demo
    main.c
    ccsds_space_packet.c
    ccsds_transfer_frame.c
    crc16.c
)

# 检查是否在Windows上编译
if(WIN32)
    # 如果是Windows，链接ws2_32库 (Windows Sockets 2)
    # 这解决了htons, ntohs等函数的链接问题
    target_link_libraries(ccsds_demo ws2_32)
endif()

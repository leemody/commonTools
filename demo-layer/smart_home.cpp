#include <iostream>
#include <unordered_map>
#include <functional>
#include <string>
#include <mutex>
#include <shared_mutex>
#include <vector>
#include <sstream>
#include <iomanip>

// ==================== 第二层：业务逻辑层（Business Layer） ====================
// 职责：实现具体的业务功能，每个业务函数独立开发、独立编译
// 这些函数会被注册到注册表中
namespace Business {
    // 灯光控制
    void lightOn(const std::string& args) {
        std::cout << "💡 灯光已打开 (亮度: 100%)\n";
        // 实际硬件控制代码会在这里
    }
    
    void lightOff(const std::string& args) {
        std::cout << "💡 灯光已关闭\n";
    }
    
    // 空调控制
    void setAirConditioner(const std::string& args) {
        if (args.empty()) {
            std::cout << "❌ 请指定温度，例: ac_set 24\n";
            return;
        }
        
        try {
            int temp = std::stoi(args);
            if (temp < 16 || temp > 30) {
                std::cout << "❌ 温度范围应在 16-30 度之间\n";
                return;
            }
            std::cout << "❄️  空调已设置为 " << temp << "°C\n";
        } catch (...) {
            std::cout << "❌ 无效的温度格式\n";
        }
    }
    
    // 窗帘控制
    void curtainUp(const std::string& args) {
        std::cout << "🪟 窗帘正在升起...\n";
        // 模拟硬件控制延时
        // 实际会调用硬件驱动
        std::cout << "✅ 窗帘已完全升起\n";
    }
    
    void curtainDown(const std::string& args) {
        std::cout << "🪟 窗帘正在降下...\n";
        std::cout << "✅ 窗帘已完全降下\n";
    }
    
    // 扩展：可以添加更多业务函数
    void getSystemStatus(const std::string& args) {
        std::cout << "📊 系统状态:\n";
        std::cout << "  CPU温度: 45°C\n";
        std::cout << "  内存使用: 128MB/512MB\n";
        std::cout << "  运行时间: 3天 5小时\n";
    }
}


// ==================== 第四层：存储层（Storage Layer） ====================
// 职责：维护全局函数注册表，提供线程安全的增删改查
// 使用 Meyers Singleton 模式避免静态初始化顺序问题
class FunctionRegistry {
public:
    // 函数类型定义：所有注册的函数必须有统一的签名
    using FunctionType = std::function<void(const std::string&)>;
    
    // 获取单例实例（Meyers Singleton - 线程安全）
    static FunctionRegistry& getInstance() {
        static FunctionRegistry instance;
        return instance;
    }
    
    // 注册函数（写操作加互斥锁）
    void registerFunction(const std::string& name, FunctionType func) {
        std::lock_guard<std::mutex> lock(mutex_);
        registry_[name] = std::move(func);
        std::cout << "[注册] 已注册命令: " << name << "\n";
    }
    
    // 获取函数（读操作加共享锁，支持并发读）
    FunctionType getFunction(const std::string& name) {
        std::shared_lock<std::shared_mutex> lock(sharedMutex_);
        auto it = registry_.find(name);
        if (it != registry_.end()) {
            return it->second;
        }
        return nullptr;
    }
    
    // 查看所有已注册的命令（用于调试）
    void listAllCommands() {
        std::shared_lock<std::shared_mutex> lock(sharedMutex_);
        std::cout << "\n📋 已注册的命令列表 (" << registry_.size() << "个):\n";
        for (const auto& [cmd, _] : registry_) {
            std::cout << "  - " << cmd << "\n";
        }
        std::cout << "\n";
    }

    // 公开删除的拷贝构造和赋值操作
    FunctionRegistry(const FunctionRegistry&) = delete;
    FunctionRegistry& operator=(const FunctionRegistry&) = delete;

private:
    FunctionRegistry() = default;  // 私有构造
    ~FunctionRegistry() = default;

    // 使用 map 或 unordered_map 存储
    std::unordered_map<std::string, FunctionType> registry_;
    
    // 互斥锁保护写操作（注册通常在 main 前完成，但为了支持动态注册仍加锁）
    std::mutex mutex_;
    
    // 读写锁保护读操作，提高并发性能
    std::shared_mutex sharedMutex_;
};


// ==================== 第三层：注册层（Registration Layer） ====================
// 职责：提供宏或工具，让业务函数自动注册到存储层
// 利用静态对象构造在 main() 之前完成注册

// 注册器类：在构造时自动将函数存入全局注册表
class Registrar {
public:
    Registrar(const std::string& name, std::function<void(const std::string&)> func);
};

// 简洁的注册宏 - 使用方式: REGISTER_FUNC(命令名, 业务函数)
// 利用宏的字符串化（#name）和符号连接（##）来创建唯一的静态变量
#define REGISTER_FUNC(name, func) \
    static Registrar registrar_##name(#name, func)

// 实现 Registrar 的构造函数
Registrar::Registrar(const std::string& name, std::function<void(const std::string&)> func) {
    FunctionRegistry::getInstance().registerFunction(name, std::move(func));
}


// ==================== 业务层注册（使用宏注册） ====================
// 这些宏调用会在静态初始化阶段自动执行
REGISTER_FUNC(light_on,      Business::lightOn);
REGISTER_FUNC(light_off,     Business::lightOff);
REGISTER_FUNC(ac_set,        Business::setAirConditioner);
REGISTER_FUNC(curtain_up,    Business::curtainUp);
REGISTER_FUNC(curtain_down,  Business::curtainDown);
REGISTER_FUNC(status,        Business::getSystemStatus);


// ==================== 第五层：调度层（Dispatch Layer） ====================
// 职责：接收命令名和参数，查找注册表并执行对应的函数
// 负责参数预处理、异常捕获、日志记录等
class Dispatcher {
public:
    static Dispatcher& getInstance() {
        static Dispatcher instance;
        return instance;
    }
    
    // 执行命令的主入口
    static bool execute(const std::string& cmd, const std::string& args) {
        // 1. 日志记录（开始）
        logCommand(cmd, args);
        
        // 2. 从注册表获取函数
        auto func = FunctionRegistry::getInstance().getFunction(cmd);
        if (!func) {
            std::cout << "[调度] 命令不存在: " << cmd << "\n";
            return false;
        }
        
        // 3. 执行函数（带异常保护）
        try {
            func(args);
            return true;
        } catch (const std::exception& e) {
            std::cout << "[调度] 执行异常: " << e.what() << "\n";
            return false;
        } catch (...) {
            std::cout << "[调度] 未知异常\n";
            return false;
        }
    }
    
    // 批量执行命令（脚本模式）
    void executeBatch(const std::vector<std::pair<std::string, std::string>>& commands) {
        std::cout << "\n🔁 批量执行模式，共 " << commands.size() << " 条指令\n";
        for (const auto& [cmd, args] : commands) {
            std::cout << "\n>>> 执行: " << cmd << " " << args << "\n";
            execute(cmd, args);
        }
    }
    
private:
    Dispatcher() = default;
    
    static void logCommand(const std::string& cmd, const std::string& args) {
        // 实际项目中可写入日志文件或远程监控
        // 这里简单输出到控制台
        std::cout << "\n[调度] 收到命令: " << cmd;
        if (!args.empty()) {
            std::cout << " 参数: " << args;
        }
        std::cout << "\n";
    }
};


// ==================== 第一层：应用层（Application Layer） ====================
// 职责：用户交互入口，接收外部输入并转换为系统能理解的命令
// 可以是：命令行、GUI、网络RPC、WebSocket等
class Application {
public:
    // 模拟从命令行读取用户输入
    static void runCommandLine() {
        std::cout << "\n======= 智能家居控制系统 =======\n";
        std::cout << "可用命令: help, light_on, light_off, ac_set, curtain_up, curtain_down, status, exit\n\n";

        std::string input;
        while (true) {
            std::cout << "> ";
            std::getline(std::cin, input);

            if (input == "exit") {
                std::cout << "系统退出\n";
                break;
            }

            if (input == "help") {
                showHelp();
                continue;
            }

            // 将原始输入转发给调度层
            processCommand(input);
        }
    }

private:
    static void processCommand(const std::string& rawInput) {
        // 简单解析：命令名 参数
        std::string cmd;
        std::string args;

        size_t spacePos = rawInput.find(' ');
        if (spacePos != std::string::npos) {
            cmd = rawInput.substr(0, spacePos);
            args = rawInput.substr(spacePos + 1);
        } else {
            cmd = rawInput;
            args = "";
        }

        // 调用调度层执行
        bool success = Dispatcher::execute(cmd, args);
        if (!success) {
            std::cout << "❌ 命令未找到或执行失败: " << cmd << "\n";
        }
    }

    static void showHelp() {
        std::cout << "\n📖 命令帮助:\n";
        std::cout << "  light_on           - 打开所有灯\n";
        std::cout << "  light_off          - 关闭所有灯\n";
        std::cout << "  ac_set <温度>      - 设置空调温度，例: ac_set 24\n";
        std::cout << "  curtain_up         - 升起窗帘\n";
        std::cout << "  curtain_down       - 放下窗帘\n";
        std::cout << "  status             - 查看系统状态\n";
        std::cout << "  help               - 显示帮助\n";
        std::cout << "  exit               - 退出系统\n\n";
    }
};


// ==================== 演示批量执行的示例 ====================
void demoBatchMode() {
    std::vector<std::pair<std::string, std::string>> batchCommands = {
        {"light_on", ""},
        {"ac_set", "24"},
        {"status", ""},
        {"curtain_up", ""},
        {"light_off", ""}
    };
    
    Dispatcher::getInstance().executeBatch(batchCommands);
}


// ==================== 主函数 ====================
int main() {
    std::cout << "🚀 系统启动\n";
    
    // 查看所有已注册的命令
    FunctionRegistry::getInstance().listAllCommands();
    
    // 演示1: 交互式命令行模式
    std::cout << "\n【模式1: 交互式命令行】\n";
    // 注意: 实际运行时解除下面的注释即可进入交互模式
    Application::runCommandLine();  // 取消注释可进入交互式命令行
    
    // 演示2: 批量执行模式（演示用）
    std::cout << "\n【模式2: 批量执行模式演示】\n";
    demoBatchMode();
    
    // 演示3: 单独执行示例
    std::cout << "\n【模式3: 单独命令示例】\n";
    Dispatcher::execute("curtain_down", "");
    Dispatcher::execute("ac_set", "26");
    
    return 0;
}

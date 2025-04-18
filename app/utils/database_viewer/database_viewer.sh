#!/bin/bash
# Helper script to demonstrate how to use the code analysis tools

# Set your repository hash here
# REPO_HASH="d305e0f2b00a5b3370c3bd8b6fa0d985afbf2ec9"  # old demo repo
REPO_HASH="df41207f7ff0563e67030b4254bfed8650202acf"  # mini demo repo
DB_URI="postgresql://codeuser:<code_password>@localhost:5432/code"

echo "Code Analysis Helper"
echo "===================="
echo

# Function to display menu
show_menu() {
    echo "What would you like to do?"
    echo "1. List all functions in the repository"
    echo "2. List only entry point functions"
    echo "3. View segments of a specific function"
    echo "4. View components of a specific function"
    echo "5. Generate function call graph"
    echo "6. Exit"
    echo
    echo -n "Enter your choice (1-6): "
}

# Main menu loop
while true; do
    show_menu
    read choice
    
    case $choice in
        1)
            echo
            echo "Listing all functions..."
            python /home/webadmin/projects/code/app/utils/database_viewer/list_functions.py --repo-hash $REPO_HASH --db-uri $DB_URI
            echo
            echo "Press Enter to continue..."
            read
            ;;
            
        2)
            echo
            echo "Listing entry point functions..."
            python /home/webadmin/projects/code/app/utils/database_viewer/list_functions.py --repo-hash $REPO_HASH --db-uri $DB_URI --entry-only
            echo
            echo "Press Enter to continue..."
            read
            ;;
            
        3)
            echo
            echo "View segments of a function"
            echo "--------------------------"
            echo "First, let's find the function..."
            
            echo -n "Enter function name (or part of name): "
            read func_name
            
            # First list matching functions
            echo
            echo "Functions matching '$func_name':"
            python /home/webadmin/projects/code/app/utils/database_viewer/list_functions.py --repo-hash $REPO_HASH --db-uri $DB_URI --filter "$func_name"
            
            # Ask for specific function ID or name
            echo
            echo -n "Enter full function name or ID to view segments: "
            read func_id
            
            # Ask if they want to organize by components
            echo
            echo -n "Organize segments by components? (y/n): "
            read by_component
            
            # View segments
            echo
            echo "Viewing segments..."
            if [[ $func_id == *":"* ]]; then
                # It's an ID
                if [[ "$by_component" == "y" || "$by_component" == "Y" ]]; then
                    python /home/webadmin/projects/code/app/utils/database_viewer/view_segments.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-id "$func_id" --show-target --by-component
                else
                    python /home/webadmin/projects/code/app/utils/database_viewer/view_segments.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-id "$func_id" --show-target
                fi
            else
                # It's a name
                if [[ "$by_component" == "y" || "$by_component" == "Y" ]]; then
                    python /home/webadmin/projects/code/app/utils/database_viewer/view_segments.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-name "$func_id" --show-target --by-component
                else
                    python /home/webadmin/projects/code/app/utils/database_viewer/view_segments.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-name "$func_id" --show-target
                fi
            fi
            
            echo
            echo "Press Enter to continue..."
            read
            ;;

        4)
            echo
            echo "View components of a function"
            echo "---------------------------"
            echo "First, let's find the function..."
            
            echo -n "Enter function name (or part of name): "
            read func_name
            
            # First list matching functions
            echo
            echo "Functions matching '$func_name':"
            python /home/webadmin/projects/code/app/utils/database_viewer/list_functions.py --repo-hash $REPO_HASH --db-uri $DB_URI --filter "$func_name"
            
            # Ask for specific function ID or name
            echo
            echo -n "Enter full function name or ID to view components: "
            read func_id
            
            # View components
            echo
            echo "Viewing components..."
            if [[ $func_id == *":"* ]]; then
                # It's an ID
                python /home/webadmin/projects/code/app/utils/database_viewer/view_components.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-id "$func_id"
            else
                # It's a name
                python /home/webadmin/projects/code/app/utils/database_viewer/view_components.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-name "$func_id"
            fi
            
            echo
            echo "Press Enter to continue..."
            read
            ;;
            
        5)
            echo
            echo "Generate Function Call Graph"
            echo "--------------------------"
            
            # Ask if they want to use a specific function or all entry points
            echo "1. Use all entry points"
            echo "2. Specify a function"
            echo -n "Enter choice (1-2): "
            read graph_choice
            
            OUTPUT_FILE="/home/webadmin/projects/code/call_graph_$(date +%s).dot"
            
            if [ "$graph_choice" == "1" ]; then
                # Use all entry points
                python /home/webadmin/projects/code/app/utils/database_viewer/function_call_graph.py --repo-hash $REPO_HASH --db-uri $DB_URI --entry-only --output-file $OUTPUT_FILE
            else
                # Ask for function name
                echo -n "Enter function name: "
                read func_name
                
                python /home/webadmin/projects/code/app/utils/database_viewer/function_call_graph.py --repo-hash $REPO_HASH --db-uri $DB_URI --function-name "$func_name" --output-file $OUTPUT_FILE
            fi
            
            # Ask if they want to generate a PNG
            echo
            echo "DOT file generated: $OUTPUT_FILE"
            echo -n "Would you like to generate a PNG image? (y/n): "
            read generate_png
            
            if [ "$generate_png" == "y" ] || [ "$generate_png" == "Y" ]; then
                PNG_FILE="${OUTPUT_FILE%.dot}.png"
                
                # Check if dot is installed
                if command -v dot &> /dev/null; then
                    dot -Tpng $OUTPUT_FILE -o $PNG_FILE
                    echo "PNG image generated: $PNG_FILE"
                else
                    echo "Graphviz 'dot' command not found. Please install Graphviz to generate images."
                    echo "Try: sudo apt-get install graphviz"
                fi
            fi
            
            echo
            echo "Press Enter to continue..."
            read
            ;;
            
        6)
            echo
            echo "Goodbye!"
            exit 0
            ;;
            
        *)
            echo
            echo "Invalid choice. Please try again."
            ;;
    esac
    
    # Clear screen for next iteration
    clear
done